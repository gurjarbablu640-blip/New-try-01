import inspect
from pathlib import Path

from config import Settings
from services.brightdata_linkedin_provider import BrightDataLinkedInProvider
from services.decision_maker_discovery import run_full_discovery_pipeline
from services.llm_provider import get_provider
from services.research_provider import ResearchProviderRouter


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_only_supported_research_providers_are_advertised():
    providers = ResearchProviderRouter()._discover_providers()
    assert [provider["name"] for provider in providers] == [
        "serper",
        "database_cache",
    ]


def test_removed_provider_configuration_is_absent():
    removed_fields = {
        "OPENAI_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "CLOUDFLARE_API_TOKEN",
        "UNOROUTER_API_KEY",
        "SEARXNG_BASE_URL",
        "DEERFLOW_BASE_URL",
        "LINKEDIN_MCP_URL",
        "APIFY_API_TOKEN",
    }
    assert removed_fields.isdisjoint(Settings.model_fields)


def test_brightdata_person_provider_is_configured_and_env_only():
    required_fields = {
        "BRIGHTDATA_API_TOKEN",
        "BRIGHTDATA_LINKEDIN_PEOPLE_SEARCH_DATASET_ID",
        "BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID",
    }
    assert required_fields.issubset(Settings.model_fields)
    assert (BACKEND_ROOT / "services" / "brightdata_linkedin_provider.py").exists()
    gitignore_path = REPO_ROOT / ".gitignore"
    if gitignore_path.exists():
        assert ".env" in gitignore_path.read_text(encoding="utf-8").splitlines()
    assert "_api_token" not in repr(BrightDataLinkedInProvider())


def test_production_person_discovery_cannot_reach_serper_or_deleted_providers():
    source = inspect.getsource(run_full_discovery_pipeline)
    assert "discover_people_with_apollo" in source
    assert "verify_apollo_candidates_with_brightdata" in source
    assert "discover_people_with_brightdata" not in source
    assert "execute_web_person_search(" not in source
    assert "research_router" not in source
    for removed in ("linkedin_mcp", "searxng", "playwright", "apify"):
        assert removed not in source.casefold()


def test_removed_runtime_modules_are_absent():
    removed_paths = [
        "backend/services/linkedin_mcp_provider.py",
        "backend/services/deerflow_adapter.py",
        "backend/services/browser_research_adapter.py",
        "backend/services/crawl4ai_pipeline.py",
        "backend/routes/scraper.py",
        "backend/services/outreachGenerator.py",
    ]
    assert all(not (REPO_ROOT / path).exists() for path in removed_paths)


def test_compose_and_backend_image_have_no_legacy_sidecars_or_browser():
    compose_path = REPO_ROOT / "docker-compose.yml"
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8").lower()
    if compose_path.exists():
        compose = compose_path.read_text(encoding="utf-8").lower()
        for removed in ("searxng", "deerflow", "linkedin_mcp", "apify"):
            assert removed not in compose
    for removed in ("playwright", "chromium"):
        assert removed not in dockerfile


def test_only_deepseek_and_gemini_can_be_constructed():
    for removed in ("openai", "groq", "openrouter", "cloudflare", "unorouter"):
        try:
            get_provider(removed)
        except ValueError:
            continue
        raise AssertionError(f"Removed provider remained constructible: {removed}")
