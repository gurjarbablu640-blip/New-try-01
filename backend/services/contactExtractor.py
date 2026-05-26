import re
import requests

from bs4 import BeautifulSoup


def extract_contacts(url):

    result = {
        "emails": [],
        "phones": [],
        "linkedin": None,
        "contact_page": None,
        "address": None,
    }

    try:

        headers = {
            "User-Agent": (
                "Mozilla/5.0"
            )
        }

        response = requests.get(
            url,
            timeout=20,
            headers=headers
        )

        html = response.text

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # ====================================================
        # EMAIL EXTRACTION
        # ====================================================

        email_pattern = (
            r"[a-zA-Z0-9._%+-]+"
            r"@[a-zA-Z0-9.-]+"
            r"\.[a-zA-Z]{2,}"
        )

        emails = re.findall(
            email_pattern,
            html
        )

        result["emails"] = list(set(emails))

        # ====================================================
        # PHONE EXTRACTION
        # ====================================================

        phone_pattern = (
            r"(?:\+91[\-\s]?)?"
            r"[6-9]\d{9}"
        )

        phones = re.findall(
            phone_pattern,
            html
        )

        result["phones"] = list(set(phones))

        # ====================================================
        # LINK EXTRACTION
        # ====================================================

        for a in soup.find_all("a", href=True):

            href = a["href"]

            if "linkedin.com" in href.lower():
                result["linkedin"] = href

            if "contact" in href.lower():

                if href.startswith("http"):

                    result["contact_page"] = href

        # ====================================================
        # SIMPLE ADDRESS DETECTION
        # ====================================================

        text = soup.get_text(" ")

        if "Vadodara" in text:
            result["address"] = "Vadodara"

        return result

    except Exception as e:

        print("CONTACT EXTRACTION ERROR:", e)

        return result