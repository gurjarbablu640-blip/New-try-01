"""LinkedIn MCP Provider — Read-Only Person Verification Adapter.

Integrates stickerdaniel/linkedin-mcp-server (pinned version 4.24.0)
as an optional, local read-only sidecar service running on http://127.0.0.1:8765/mcp.

Strict Safety Tenets:
1. Deny By Default:
   Only tools in READ_ONLY_ALLOWLIST are permitted.
   Action tools (connect_with_person, send_message, like, comment, post) are
   strictly blocked locally BEFORE making any network call.
2. Zero Credentials in Salesoorja:
   No LinkedIn passwords, cookies, or session files are stored in Salesoorja.
   Authentication is managed externally by the user in the local MCP browser profile.
3. Concurrency = 1:
   Thread lock serializes all MCP operations to preserve local browser session integrity.
4. Senior Authority Priority:
   Search order prioritizes senior decision-makers (Plant Head, Head Quality, QA Head,
   Metrology Head, GM Quality) before generic quality ICs.
5. Salesoorja Gates Remain Authoritative:
   LinkedIn MCP provides structured evidence (profile URL, company, title, dates,
   locations, experience entries). All final qualification decisions remain strictly
   deterministic in Salesoorja truth gates.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Pinned third-party LinkedIn MCP package version
PINNED_LINKEDIN_MCP_VERSION = "4.24.0"

# Strict Read-Only Tool Allowlist (Deny by default)
READ_ONLY_ALLOWLIST: Set[str] = {
    "get_company_profile",
    "get_company_employees",
    "search_people",
    "get_person_profile",
    "get_company_posts",
    "search_posts",
}

# Explicit Blocklist for Action / Mutation Tools
BLOCKED_ACTION_TOOLS: Set[str] = {
    "connect_with_person",
    "send_message",
    "like_post",
    "comment_on_post",
    "create_post",
    "close_session",
}

# Senior Authority Hierarchy for Decision-Maker Search (Order of Priority)
SENIOR_AUTHORITY_ROLE_ORDER: List[str] = [
    "Plant Head",
    "Factory Head",
    "Unit Head",
    "Head Quality",
    "Plant Quality Head",
    "QA Head",
    "QC Head",
    "Metrology Head",
    "Calibration Head",
    "GM Quality",
    "AGM Quality",
    "Manufacturing Head",
    "Operations Head",
    "Instrumentation Head",
    "Maintenance Head",
    "Senior Quality Manager",
    "Quality Manager",
]

FALLBACK_IC_KEYWORDS: List[str] = [
    "Quality Engineer",
    "QA Engineer",
    "Quality Executive",
    "Assistant Manager Quality",
]


class LinkedInMCPError(Exception):
    """Base exception for LinkedIn MCP provider errors."""
    pass


class LinkedInMCPActionBlockedError(LinkedInMCPError):
    """Raised when an action or unapproved tool is requested."""
    pass


class LinkedInMCPAuthError(LinkedInMCPError):
    """Raised when authentication is required or security challenge presented."""
    pass


class LinkedInMCPRateLimitError(LinkedInMCPError):
    """Raised when LinkedIn rate limits or throttles requests."""
    pass


class LinkedInMCPUnavailableError(LinkedInMCPError):
    """Raised when local MCP server is offline or unreachable."""
    pass


class LinkedInMCPInitializationTimeoutError(LinkedInMCPError):
    """Raised when TCP connects but the MCP initialize lifecycle times out."""
    pass


class LinkedInMCPSessionError(LinkedInMCPError):
    """Raised when MCP initialization does not establish a usable session."""
    pass


class LinkedInMCPHostRejectedError(LinkedInMCPError):
    """Raised when strict MCP Host/Origin protection rejects the request."""
    pass


class LinkedInMCPProvider:
    """Read-only client and adapter for local LinkedIn MCP Streamable HTTP server."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        host_header: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout_seconds: Optional[int] = None,
        max_candidates: Optional[int] = None,
    ) -> None:
        self._explicit_endpoint = endpoint_url
        self._explicit_host_header = host_header
        self._explicit_enabled = enabled
        self._explicit_timeout = timeout_seconds
        self._explicit_max_candidates = max_candidates
        self._lock = threading.Lock()
        self._initialization_lock = threading.Lock()
        self._company_cache: Dict[str, Dict[str, Any]] = {}
        self._request_counter = 0
        self._session_id: Optional[str] = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        if self._explicit_enabled is not None:
            return bool(self._explicit_enabled)
        try:
            from config import settings
            return bool(getattr(settings, "LINKEDIN_MCP_ENABLED", False))
        except Exception:
            return False

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._explicit_enabled = value

    @enabled.deleter
    def enabled(self) -> None:
        self._explicit_enabled = None

    @property
    def endpoint_url(self) -> str:
        if self._explicit_endpoint is not None:
            return str(self._explicit_endpoint)
        try:
            from config import settings
            return str(getattr(settings, "LINKEDIN_MCP_URL", "http://127.0.0.1:8765/mcp"))
        except Exception:
            return "http://127.0.0.1:8765/mcp"

    @property
    def timeout_seconds(self) -> int:
        if self._explicit_timeout is not None:
            return int(self._explicit_timeout)
        try:
            from config import settings
            return int(getattr(settings, "LINKEDIN_MCP_TIMEOUT_SECONDS", 180))
        except Exception:
            return 180

    @property
    def host_header(self) -> str:
        if self._explicit_host_header is not None:
            value = str(self._explicit_host_header).strip()
        else:
            try:
                from config import settings
                value = str(getattr(settings, "LINKEDIN_MCP_HOST_HEADER", "") or "").strip()
            except Exception:
                value = ""

        if value and not re.fullmatch(r"(?:127\.0\.0\.1|localhost)(?::\d{1,5})?", value, re.IGNORECASE):
            raise LinkedInMCPError(
                "LINKEDIN_MCP_HOST_HEADER must remain loopback-only (127.0.0.1 or localhost)."
            )
        return value

    @property
    def max_candidates(self) -> int:
        if self._explicit_max_candidates is not None:
            return int(self._explicit_max_candidates)
        try:
            from config import settings
            return int(getattr(settings, "LINKEDIN_MCP_MAX_CANDIDATES", 3))
        except Exception:
            return 3

    def get_status(self) -> Dict[str, Any]:
        """Check provider status and server connectivity.

        Returns status in: READY, DISABLED, SERVER_UNAVAILABLE, LOGIN_REQUIRED,
        MANUAL_BROWSER_ACTION_REQUIRED, RATE_LIMITED, TOOL_ERROR, TIMEOUT.
        """
        if not self.enabled:
            return {"status": "DISABLED", "message": "LinkedIn MCP is disabled in configuration."}

        try:
            with self._lock:
                res = self._send_jsonrpc("tools/list", {})
            tools = [t.get("name") for t in res.get("tools", []) if isinstance(t, dict)]
            return {
                "status": "READY",
                "message": "LinkedIn MCP server is connected and operational.",
                "tools_available": [t for t in tools if t in READ_ONLY_ALLOWLIST],
                "endpoint": self.endpoint_url,
                "pinned_version": PINNED_LINKEDIN_MCP_VERSION,
            }
        except LinkedInMCPAuthError as e:
            msg = str(e)
            if "challenge" in msg.lower() or "captcha" in msg.lower():
                return {"status": "MANUAL_BROWSER_ACTION_REQUIRED", "message": msg}
            return {"status": "LOGIN_REQUIRED", "message": msg}
        except LinkedInMCPRateLimitError as e:
            return {"status": "RATE_LIMITED", "message": str(e)}
        except LinkedInMCPInitializationTimeoutError as e:
            return {"status": "MCP_INITIALIZATION_TIMEOUT", "message": str(e)}
        except LinkedInMCPHostRejectedError as e:
            return {"status": "MCP_HOST_REJECTED", "message": str(e)}
        except LinkedInMCPSessionError as e:
            return {"status": "MCP_SESSION_ERROR", "message": str(e)}
        except LinkedInMCPUnavailableError as e:
            return {"status": "SERVER_UNAVAILABLE", "message": str(e)}
        except Exception as e:
            return {"status": "TOOL_ERROR", "message": str(e)}

    def invoke_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke a tool through MCP Streamable HTTP protocol with strict allowlist enforcement."""
        # 1. Strict Allowlist Enforcement (Deny by Default)
        if tool_name not in READ_ONLY_ALLOWLIST:
            err_msg = (
                f"Tool '{tool_name}' is not in the Salesoorja LinkedIn MCP read-only allowlist. "
                f"Action and mutation tools are strictly blocked by policy."
            )
            logger.error("BLOCKED ACTION ATTEMPT: %s", err_msg)
            raise LinkedInMCPActionBlockedError(err_msg)

        if tool_name in BLOCKED_ACTION_TOOLS:
            err_msg = f"Tool '{tool_name}' is explicitly blocked by Salesoorja safety boundary."
            logger.error("BLOCKED MUTATION ATTEMPT: %s", err_msg)
            raise LinkedInMCPActionBlockedError(err_msg)

        # 2. Concurrency = 1 serialization
        with self._lock:
            payload = {
                "name": tool_name,
                "arguments": arguments,
            }
            res = self._send_jsonrpc("tools/call", payload)
            # FastMCP tools/call returns {"content": [{"type": "text", "text": "..."}], "isError": bool}
            if isinstance(res, dict):
                if res.get("isError"):
                    err_text = ""
                    for c in res.get("content", []):
                        if isinstance(c, dict) and c.get("text"):
                            err_text += str(c["text"]) + " "
                    self._classify_and_raise_error(err_text or "Tool call failed.")

                structured_content = res.get("structuredContent") or res.get("structured_content")
                if isinstance(structured_content, dict):
                    if set(structured_content) == {"result"}:
                        return structured_content["result"]
                    return structured_content

                content_items = res.get("content", [])
                if content_items and isinstance(content_items, list):
                    first_text = content_items[0].get("text", "")
                    # Try parsing JSON if content is stringified JSON
                    try:
                        return json.loads(first_text)
                    except (TypeError, ValueError):
                        return first_text
            return res

    def _send_jsonrpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON-RPC 2.0 request over Streamable HTTP transport."""
        self._ensure_initialized()
        self._request_counter += 1
        req_id = self._request_counter

        body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        headers = self._request_headers(include_session=True)

        try:
            resp = requests.post(
                self.endpoint_url,
                json=body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.exceptions.ConnectionError as e:
            raise LinkedInMCPUnavailableError(
                f"Cannot connect to LinkedIn MCP server at {self.endpoint_url}. "
                f"Verify sidecar is running via: uvx mcp-server-linkedin@{PINNED_LINKEDIN_MCP_VERSION} --transport streamable-http --port 8765"
            ) from e
        except requests.exceptions.Timeout as e:
            raise LinkedInMCPError(f"LinkedIn MCP request timed out after {self.timeout_seconds}s.") from e
        except Exception as e:
            raise LinkedInMCPError(f"LinkedIn MCP transport error: {type(e).__name__} - {e}") from e

        return self._parse_http_response(resp)

    def _ensure_initialized(self) -> None:
        """Complete the MCP Streamable HTTP initialization lifecycle once."""
        if self._initialized:
            return

        with self._initialization_lock:
            if self._initialized:
                return

            self._request_counter += 1
            initialize_body = {
                "jsonrpc": "2.0",
                "id": self._request_counter,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "salesoorja-linkedin-adapter",
                        "version": "1.0",
                    },
                },
            }

            try:
                response = requests.post(
                    self.endpoint_url,
                    json=initialize_body,
                    headers=self._request_headers(include_session=False),
                    timeout=self.timeout_seconds,
                )
            except requests.exceptions.ConnectionError as e:
                raise LinkedInMCPUnavailableError(
                    f"Cannot connect to LinkedIn MCP server at {self.endpoint_url}."
                ) from e
            except requests.exceptions.Timeout as e:
                raise LinkedInMCPInitializationTimeoutError(
                    f"MCP initialize request timed out after {self.timeout_seconds}s."
                ) from e
            except Exception as e:
                raise LinkedInMCPError(
                    f"LinkedIn MCP initialize transport error: {type(e).__name__} - {e}"
                ) from e

            self._parse_http_response(response)
            session_id = response.headers.get("mcp-session-id")
            if not session_id:
                raise LinkedInMCPSessionError(
                    "MCP initialize response did not include the required Mcp-Session-Id header."
                )

            self._session_id = str(session_id)
            self._request_counter += 1
            initialized_body = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }

            try:
                initialized_response = requests.post(
                    self.endpoint_url,
                    json=initialized_body,
                    headers=self._request_headers(include_session=True),
                    timeout=self.timeout_seconds,
                )
            except requests.exceptions.Timeout as e:
                self._session_id = None
                raise LinkedInMCPInitializationTimeoutError(
                    f"MCP initialized notification timed out after {self.timeout_seconds}s."
                ) from e
            except requests.exceptions.ConnectionError as e:
                self._session_id = None
                raise LinkedInMCPUnavailableError(
                    f"Connection lost while establishing MCP session at {self.endpoint_url}."
                ) from e
            except Exception as e:
                self._session_id = None
                raise LinkedInMCPError(
                    f"MCP session establishment error: {type(e).__name__} - {e}"
                ) from e

            if initialized_response.status_code not in {200, 202, 204}:
                self._session_id = None
                self._parse_http_response(initialized_response)
                raise LinkedInMCPSessionError(
                    f"MCP initialized notification returned HTTP {initialized_response.status_code}."
                )

            self._initialized = True

    def _request_headers(self, *, include_session: bool) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "SalesoorjaLinkedInAdapter/1.0",
        }
        if include_session:
            if not self._session_id:
                raise LinkedInMCPSessionError("MCP session ID is not available.")
            headers["Mcp-Session-Id"] = self._session_id
        if self.host_header:
            headers["Host"] = self.host_header
        return headers

    def _parse_http_response(self, resp: requests.Response) -> Dict[str, Any]:
        """Parse one MCP JSON or SSE response and classify protocol errors."""
        raw_text = resp.text
        if resp.status_code == 421 or (
            resp.status_code in {400, 403}
            and any(token in raw_text.lower() for token in ["misdirected", "invalid host", "host not allowed", "origin not allowed"])
        ):
            raise LinkedInMCPHostRejectedError(
                f"LinkedIn MCP rejected the HTTP Host/Origin header with status {resp.status_code}."
            )
        if resp.status_code == 429:
            raise LinkedInMCPRateLimitError("LinkedIn MCP returned HTTP 429 Too Many Requests. Pausing operations.")

        # Check for SSE stream responses
        if "data:" in raw_text:
            parsed_data = self._parse_sse_response(raw_text)
            if parsed_data:
                return self._handle_jsonrpc_result(parsed_data)

        try:
            res_json = resp.json()
            return self._handle_jsonrpc_result(res_json)
        except Exception:
            self._classify_and_raise_error(raw_text)
            raise LinkedInMCPError(f"Unexpected response from LinkedIn MCP: {raw_text[:300]}")

    def _handle_jsonrpc_result(self, res_json: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(res_json, dict):
            raise LinkedInMCPError(f"Invalid JSON-RPC response type: {type(res_json)}")

        if "error" in res_json and res_json["error"]:
            err_obj = res_json["error"]
            err_msg = str(err_obj.get("message") or err_obj)
            self._classify_and_raise_error(err_msg)
            raise LinkedInMCPError(f"LinkedIn MCP JSON-RPC Error: {err_msg}")

        return res_json.get("result") or {}

    def _parse_sse_response(self, sse_text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON payload from Server-Sent Events stream."""
        for line in sse_text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                json_part = line[len("data:"):].strip()
                if json_part:
                    try:
                        return json.loads(json_part)
                    except Exception:
                        continue
        return None

    def _classify_and_raise_error(self, message: str) -> None:
        """Classify server error messages into specific safety states."""
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["captcha", "challenge", "checkpoint", "security verification", "otp"]):
            raise LinkedInMCPAuthError(f"LinkedIn presented security challenge: {message}")
        if any(w in msg_lower for w in ["login required", "sign in", "not logged in", "session expired", "unauthorized"]):
            raise LinkedInMCPAuthError(f"LinkedIn authentication required: {message}")
        if any(w in msg_lower for w in ["rate limit", "too many requests", "429", "throttled", "wait before retrying"]):
            raise LinkedInMCPRateLimitError(f"LinkedIn rate limit reached: {message}")

    # ── High-Level Business Domain Operations ─────────────────────────────────

    @staticmethod
    def _section_text(payload: Dict[str, Any], section: str) -> str:
        sections = payload.get("sections") or {}
        return str(sections.get(section) or "") if isinstance(sections, dict) else ""

    @staticmethod
    def _section_references(payload: Dict[str, Any], section: str) -> List[Dict[str, Any]]:
        references = payload.get("references") or {}
        items = references.get(section, []) if isinstance(references, dict) else []
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    @staticmethod
    def _absolute_linkedin_url(url: str) -> str:
        clean_url = str(url or "").strip()
        return f"https://www.linkedin.com{clean_url}" if clean_url.startswith("/") else clean_url

    @classmethod
    def _extract_people_items(cls, payload: Any, direct_key: str) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        direct_items = payload.get(direct_key)
        if isinstance(direct_items, list):
            return [item for item in direct_items if isinstance(item, dict)]
        section = "search_results" if direct_key == "results" else "employees"
        items: List[Dict[str, Any]] = []
        for reference in cls._section_references(payload, section):
            if reference.get("kind") != "person":
                continue
            items.append({
                "name": str(reference.get("text") or "").strip(),
                "headline": str(reference.get("context") or "").strip(),
                "profile_url": cls._absolute_linkedin_url(str(reference.get("url") or "")),
                "location": "",
            })
        return items

    @staticmethod
    def _parse_profile_lines(text: str) -> List[str]:
        return [line.strip() for line in str(text or "").splitlines() if line.strip()]

    @classmethod
    def _parse_experience_section(cls, text: str, target_company: str) -> List[Dict[str, Any]]:
        lines = cls._parse_profile_lines(text)
        target_tokens = [
            token for token in re.findall(r"[a-z0-9]+", target_company.lower())
            if token not in {"limited", "ltd", "private", "pvt", "inc", "corp", "corporation"}
        ]
        experiences: List[Dict[str, Any]] = []
        for index, line in enumerate(lines):
            if not target_tokens or not all(token in line.lower() for token in target_tokens[:2]):
                continue
            title = lines[index - 1] if index > 0 and lines[index - 1].lower() != "experience" else ""
            following = lines[index + 1:index + 7]
            dates = next((item for item in following if re.search(r"\b(?:19|20)\d{2}\b", item)), "")
            date_index = following.index(dates) if dates in following else -1
            after_dates = following[date_index + 1:] if date_index >= 0 else following
            location = next((item for item in after_dates if "," in item or "india" in item.lower()), "")
            description = " ".join(item for item in after_dates if item != location)[:200]
            experiences.append({
                "company": line.split("·", 1)[0].strip(),
                "title": title,
                "dates": dates,
                "is_current": "present" in dates.lower() or "current" in dates.lower(),
                "location": location,
                "description": description,
            })
        return experiences

    def resolve_company(self, company_name: str, domain: str = "") -> Optional[Dict[str, Any]]:
        """Resolve company profile on LinkedIn and extract slug and numeric company_urn."""
        clean_name = re.sub(r"\b(limited|ltd|private|pvt|corp|corporation|inc)\b", "", company_name.lower()).strip()
        cache_key = clean_name
        if cache_key in self._company_cache:
            return self._company_cache[cache_key]

        # Extract slug from domain or clean name
        company_query = re.sub(r"[^a-z0-9]+", "-", clean_name).strip("-")
        if not company_query and domain:
            company_query = domain.lower().removeprefix("www.").split(".")[0]

        try:
            profile_data = self.invoke_tool("get_company_profile", {"company_name": company_query})
        except (LinkedInMCPAuthError, LinkedInMCPRateLimitError):
            raise
        except Exception as e:
            logger.warning("Could not resolve company '%s' on LinkedIn MCP: %s", company_name, e)
            return None

        if not isinstance(profile_data, dict):
            return None

        # Extract numeric URN from about section or company_urn entry
        raw_urn = str(profile_data.get("company_urn") or profile_data.get("urn") or "")
        for reference in self._section_references(profile_data, "about"):
            if reference.get("kind") == "company_urn" and reference.get("value"):
                raw_urn = str(reference["value"])
                break
        m_digits = re.search(r"(\d+)", raw_urn)
        if m_digits:
            company_urn = m_digits.group(1)
        else:
            # Search text for urn:li:fsd_company:<id> or urn:li:company:<id>
            m_urn = re.search(r"urn:li:(?:company|fsd_company):(\d+)", str(profile_data))
            company_urn = m_urn.group(1) if m_urn else raw_urn

        company_url = str(profile_data.get("url") or "")
        slug_match = re.search(r"linkedin\.com/company/([^/?#]+)", company_url, re.IGNORECASE)
        slug = str(profile_data.get("universal_name") or profile_data.get("slug") or (slug_match.group(1) if slug_match else company_query))
        result = {
            "company_name": profile_data.get("name") or company_name,
            "company_slug": slug,
            "company_urn": company_urn,
            "employee_count": profile_data.get("employee_count"),
            "website": profile_data.get("website") or domain,
            "headline": profile_data.get("headline") or profile_data.get("tagline") or "",
            "company_url": company_url or f"https://www.linkedin.com/company/{slug}/",
        }
        self._company_cache[cache_key] = result
        return result

    def search_decision_makers(
        self,
        company_name: str,
        company_urn: Optional[str] = None,
        company_slug: Optional[str] = None,
        city: Optional[str] = None,
        facility_name: Optional[str] = None,
        max_candidates: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for senior plant decision-makers prioritized by authority hierarchy."""
        limit = max_candidates or self.max_candidates
        candidates: List[Dict[str, Any]] = []
        seen_profile_urls: Set[str] = set()

        # Target company identifier for LinkedIn search (numeric URN preferred)
        comp_target = company_urn if company_urn and str(company_urn).isdigit() else None
        company_keywords = f' "{company_name}"' if not comp_target else ""

        # Priority 1: Senior Authority Roles (Plant Head, Head Quality, QA Head, Metrology Head)
        senior_query = '("Plant Head" OR "Factory Head" OR "Unit Head" OR "Head Quality" OR "Plant Quality Head" OR "QA Head" OR "Metrology")' + company_keywords
        try:
            search_args: Dict[str, Any] = {
                "keywords": senior_query,
            }
            if comp_target:
                search_args["current_company"] = comp_target
            if city:
                search_args["location"] = city

            raw_results = self.invoke_tool("search_people", search_args)
            items = self._extract_people_items(raw_results, "results")

            for item in items:
                if not isinstance(item, dict):
                    continue
                p_url = str(item.get("profile_url") or item.get("url") or "")
                if p_url and p_url not in seen_profile_urls:
                    seen_profile_urls.add(p_url)
                    parsed = self._normalize_search_candidate(item, authority_tier="SENIOR")
                    candidates.append(parsed)
                    if len(candidates) >= limit:
                        break
        except (LinkedInMCPAuthError, LinkedInMCPRateLimitError):
            raise
        except Exception as e:
            logger.warning("Senior people search failed on LinkedIn MCP: %s", e)

        # Priority 2: Quality Leadership Managers if slots remain
        if len(candidates) < limit:
            mgr_query = '("Quality Manager" OR "Operations Manager" OR "Maintenance Head")' + company_keywords
            try:
                search_args = {
                    "keywords": mgr_query,
                }
                if comp_target:
                    search_args["current_company"] = comp_target
                if city:
                    search_args["location"] = city

                raw_results = self.invoke_tool("search_people", search_args)
                items = self._extract_people_items(raw_results, "results")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    p_url = str(item.get("profile_url") or item.get("url") or "")
                    if p_url and p_url not in seen_profile_urls:
                        seen_profile_urls.add(p_url)
                        parsed = self._normalize_search_candidate(item, authority_tier="MANAGER")
                        candidates.append(parsed)
                        if len(candidates) >= limit:
                            break
            except (LinkedInMCPAuthError, LinkedInMCPRateLimitError):
                raise
            except Exception as e:
                logger.warning("Manager search failed on LinkedIn MCP: %s", e)

        # Priority 3: Company Employees endpoint fallback
        if len(candidates) < limit:
            try:
                employee_company = company_slug or re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")
                employee_company = re.sub(r"-(?:limited|ltd|private|pvt)$", "", employee_company).strip("-")
                emp_results = self.invoke_tool(
                    "get_company_employees",
                    {"company_name": employee_company, "keywords": "Quality"},
                )
                items = self._extract_people_items(emp_results, "employees")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    p_url = str(item.get("profile_url") or item.get("url") or "")
                    if p_url and p_url not in seen_profile_urls:
                        seen_profile_urls.add(p_url)
                        parsed = self._normalize_search_candidate(item, authority_tier="EMPLOYEE_FALLBACK")
                        candidates.append(parsed)
                        if len(candidates) >= limit:
                            break
            except (LinkedInMCPAuthError, LinkedInMCPRateLimitError):
                raise
            except Exception as e:
                logger.debug("Company employees search fallback failed: %s", e)

        return candidates[:limit]

    def verify_candidate_experience(
        self,
        profile_url: str,
        target_company: str,
        target_facility: str = "",
        target_city: str = "",
    ) -> Dict[str, Any]:
        """Fetch and parse Experience section of candidate profile to ground employment and facility truth.

        Strict Principles:
        - Experience entries parsed directly (not just headline).
        - Contradiction overrides corroboration: If latest/current experience is at a different employer,
          status is CONTRADICTED.
        - Generic profile location != DIRECT facility ownership. DIRECT requires plant name or job location
          tied to that specific experience entry.
        """
        try:
            profile_data = self.invoke_tool(
                "get_person_profile",
                {"linkedin_username": profile_url, "sections": "experience"},
            )
        except (LinkedInMCPAuthError, LinkedInMCPRateLimitError):
            raise
        except Exception as e:
            logger.warning("Failed to get profile experience for %s: %s", profile_url, e)
            return {
                "profile_url": profile_url,
                "current_employment": "UNKNOWN",
                "facility_relationship": "UNKNOWN",
                "is_contradicted": False,
                "experiences": [],
                "error": str(e),
            }

        if not isinstance(profile_data, dict):
            return {
                "profile_url": profile_url,
                "current_employment": "UNKNOWN",
                "facility_relationship": "UNKNOWN",
                "is_contradicted": False,
                "experiences": [],
            }

        main_profile_lines = self._parse_profile_lines(self._section_text(profile_data, "main_profile"))
        name = profile_data.get("name") or profile_data.get("full_name") or (main_profile_lines[0] if main_profile_lines else "")
        headline = profile_data.get("headline") or (main_profile_lines[1] if len(main_profile_lines) > 1 else "")
        profile_location = profile_data.get("location") or profile_data.get("geo_location") or next((line for line in main_profile_lines[2:8] if "," in line), "")
        experiences_raw = profile_data.get("experience") or profile_data.get("experiences") or self._parse_experience_section(
            self._section_text(profile_data, "experience"),
            target_company,
        )

        # Target company matching helper
        comp_clean = re.sub(r"\b(limited|ltd|private|pvt|corp|corporation|inc)\b", "", target_company.lower()).strip()
        base_comp = re.sub(
            r"\s+(?:India|Technologies|Solutions|Industries|Limited|Ltd|Pvt\s+Ltd|Private\s+Limited)\b.*",
            "",
            target_company,
            flags=re.IGNORECASE,
        ).strip().lower()

        def is_target_comp(c_name: str) -> bool:
            c_low = (c_name or "").lower()
            if comp_clean and comp_clean[:6] in c_low:
                return True
            if base_comp and len(base_comp) >= 3 and base_comp in c_low:
                return True
            return False

        parsed_experiences: List[Dict[str, Any]] = []
        is_contradicted = False
        target_present_exp = None
        other_current_exp = None

        for idx, exp in enumerate(experiences_raw if isinstance(experiences_raw, list) else []):
            if not isinstance(exp, dict):
                continue
            exp_comp = str(exp.get("company") or exp.get("company_name") or "")
            exp_title = str(exp.get("title") or exp.get("role") or "")
            exp_dates = str(exp.get("date_range") or exp.get("dates") or exp.get("duration") or "")
            exp_loc = str(exp.get("location") or "")
            is_present = bool(
                exp.get("is_current")
                or "present" in exp_dates.lower()
                or "current" in exp_dates.lower()
                or not exp.get("end_date") and exp.get("start_date")
            )

            exp_record = {
                "company": exp_comp,
                "title": exp_title,
                "dates": exp_dates,
                "is_current": is_present,
                "location": exp_loc,
                "description": str(exp.get("description") or "")[:200],
            }
            parsed_experiences.append(exp_record)

            # Check if this is a current role
            if is_present:
                if is_target_comp(exp_comp):
                    target_present_exp = exp_record
                else:
                    # Current role at another employer!
                    if idx == 0:  # Primary/latest role
                        other_current_exp = exp_record

        # Determine current employment status
        target_idx = None
        other_current_idx = None
        for idx, exp in enumerate(parsed_experiences):
            if exp == target_present_exp and target_idx is None:
                target_idx = idx
            if exp == other_current_exp and other_current_idx is None:
                other_current_idx = idx

        if other_current_exp and (target_present_exp is None or (target_idx is not None and other_current_idx is not None and other_current_idx < target_idx)):
            current_employment = "CONTRADICTED"
            is_contradicted = True
        elif target_present_exp:
            current_employment = "VERIFIED"
        elif any(is_target_comp(e["company"]) for e in parsed_experiences):
            # Target company in past experiences only
            current_employment = "CONTRADICTED"
            is_contradicted = True
        else:
            current_employment = "UNKNOWN"

        # Determine facility relationship (Correction 1: Generic profile location != DIRECT facility ownership)
        facility_relationship = "COMPANY_ONLY"
        t_city = target_city.lower().strip() if target_city else ""
        t_fac = target_facility.lower().strip() if target_facility else ""

        # Retrieve metro cluster for target city (e.g. Sanand <-> Ahmedabad, Kongara Kalan <-> Hyderabad)
        metro_cluster: Set[str] = set()
        try:
            from services.person_intelligence_service import METRO_CLUSTERS
            metro_cluster = METRO_CLUSTERS.get(t_city, set())
        except Exception:
            metro_cluster = set()

        if target_present_exp:
            exp_text = f"{headline} {target_present_exp['title']} {target_present_exp['location']} {target_present_exp['description']}".lower()

            # DIRECT requires plant name or job location tied specifically to this experience
            has_direct_plant = bool(t_fac and any(w in exp_text for w in t_fac.split() if len(w) >= 4 and w not in ["plant", "works", "facility", "unit"]))
            has_plant_keyword = any(w in exp_text for w in ["plant", "works", "factory", "unit", "manufacturing site"])
            has_direct_city = bool(t_city and t_city in target_present_exp["location"].lower())

            if has_direct_plant or (has_direct_city and has_plant_keyword):
                facility_relationship = "FACILITY_FUNCTION_OWNER"
            elif t_city and t_city in target_present_exp["location"].lower():
                facility_relationship = "STRONG"
            elif profile_location and (
                (t_city and t_city in profile_location.lower())
                or any(m in profile_location.lower() for m in metro_cluster)
            ):
                # Profile location only supports STRONG (metro/residence), never DIRECT!
                facility_relationship = "STRONG"
            elif any(c in profile_location.lower() for c in ["ahmedabad", "pune", "chennai", "bengaluru", "hyderabad", "mumbai"]):
                # Known Indian industrial metro
                facility_relationship = "COMPANY_ONLY"
            else:
                facility_relationship = "COMPANY_ONLY"

        # Extract current title
        active_title = (
            target_present_exp["title"] if target_present_exp
            else (headline or (parsed_experiences[0]["title"] if parsed_experiences else ""))
        )

        # Classify function and authority separately (Correction 8)
        combined_role_text = f"{active_title} {headline}".lower()
        function_verified = any(
            fn in combined_role_text
            for fn in [
                "quality", "qa", "qc", "metrology", "calibration",
                "inspection", "testing", "plant head", "factory head",
                "unit head", "operations", "manufacturing", "maintenance",
                "instrumentation",
            ]
        )
        authority_verified = any(
            re.search(rf"\b{re.escape(role.lower())}\b", combined_role_text)
            for role in SENIOR_AUTHORITY_ROLE_ORDER
        ) or any(w in combined_role_text for w in ["head", "director", "gm", "general manager", "plant head", "factory head", "unit head", "vice president", "vp"])

        return {
            "name": name,
            "headline": headline,
            "profile_url": profile_url,
            "current_title": active_title,
            "current_company": target_company if target_present_exp else (other_current_exp["company"] if other_current_exp else ""),
            "profile_location": profile_location,
            "current_employment": current_employment,
            "facility_relationship": facility_relationship,
            "function_verified": function_verified,
            "authority_verified": authority_verified,
            "is_contradicted": is_contradicted,
            "target_experience": target_present_exp,
            "other_current_experience": other_current_exp,
            "experiences": parsed_experiences,
        }

    def _normalize_search_candidate(self, raw_item: Dict[str, Any], authority_tier: str) -> Dict[str, Any]:
        """Normalize raw people search item into structured Salesoorja candidate representation."""
        name = str(raw_item.get("name") or raw_item.get("title") or "").strip()
        headline = str(raw_item.get("headline") or raw_item.get("role") or "").strip()
        url = str(raw_item.get("profile_url") or raw_item.get("url") or "").strip()
        location = str(raw_item.get("location") or "").strip()

        return {
            "name": name,
            "title": headline,
            "profile_url": url,
            "location": location,
            "authority_tier": authority_tier,
            "source_type": "LINKEDIN_PROFILE",
            "source_provenance": "LINKEDIN_MCP",
        }


# Global singleton provider instance
linkedin_mcp_provider = LinkedInMCPProvider()
