import os

import google.generativeai as genai


GOOGLE_API_KEY = os.getenv(
    "GOOGLE_API_KEY"
)

if GOOGLE_API_KEY:

    genai.configure(
        api_key=GOOGLE_API_KEY
    )


def score_company(company):

    try:

        model = genai.GenerativeModel(
            "gemini-1.5-flash"
        )

        prompt = f"""
        You are an industrial sales ICP scorer.

        Evaluate this company for calibration
        and testing service potential.

        Company:
        {company.name}

        Industry:
        {company.industry}

        Website:
        {company.website}

        City:
        {company.city}

        Return ONLY a score from 1 to 100.

        Scoring Logic:
        - Manufacturing = high
        - Pharma = high
        - Electrical = high
        - Industrial automation = high
        - Transformer companies = high
        - Small traders = low
        - Retail = low
        """

        response = model.generate_content(
            prompt
        )

        score_text = response.text.strip()

        score = int(
            ''.join(
                filter(str.isdigit, score_text)
            )
        )

        score = max(
            1,
            min(score, 100)
        )

        return score

    except Exception as e:

        print("ICP SCORE ERROR:", e)

        return 50