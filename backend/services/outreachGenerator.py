import os

import google.generativeai as genai


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)


def generate_outreach(company):

    try:

        model = genai.GenerativeModel(
            "gemini-1.5-flash"
        )

        prompt = f"""
        Generate a professional cold outreach message.

        Company:
        {company.name}

        Industry:
        {company.industry}

        City:
        {company.city}

        We provide:
        Calibration Services
        NABL Calibration
        Testing Services

        Generate:

        1. Cold Email
        2. LinkedIn Message
        3. WhatsApp Intro

        Keep it practical and sales-oriented.
        """

        response = model.generate_content(
            prompt
        )

        return response.text

    except Exception as e:

        print("OUTREACH ERROR:", e)

        return "Could not generate outreach."