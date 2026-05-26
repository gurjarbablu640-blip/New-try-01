import os

from fastapi import APIRouter

from pydantic import BaseModel

from sqlalchemy.orm import Session

from apify_client import ApifyClient

from database import SessionLocal

from models.company import Company

from services.contactExtractor import (
    extract_contacts
)

from services.icpScorer import (
    score_company
)


router = APIRouter(
    prefix="/api/scraper",
    tags=["Scraper"]
)


# ============================================================
# ENV VARIABLES
# ============================================================

APIFY_API_TOKEN = os.getenv(
    "APIFY_API_TOKEN"
)


# ============================================================
# REQUEST MODEL
# ============================================================

class ScrapeRequest(BaseModel):

    query: str


# ============================================================
# GOOGLE MAPS SCRAPER
# ============================================================

@router.post("/google")
async def scrape_google(data: ScrapeRequest):

    print(
        "========== SCRAPER STARTED =========="
    )

    if not APIFY_API_TOKEN:

        print("APIFY TOKEN MISSING")

        return {
            "success": False,
            "error":
                "APIFY_API_TOKEN missing in .env"
        }

    print("APIFY TOKEN FOUND")

    db: Session = SessionLocal()

    inserted = 0

    skipped = 0

    results = []

    try:

        # ====================================================
        # CREATE APIFY CLIENT
        # ====================================================

        client = ApifyClient(
            APIFY_API_TOKEN
        )

        print("APIFY CLIENT CREATED")

        # ====================================================
        # APIFY INPUT
        # ====================================================

        run_input = {

            "searchStringsArray": [
                data.query
            ],

            "maxCrawledPlacesPerSearch": 10,

            "language": "en",
        }

        print(
            "RUN INPUT:",
            run_input
        )

        # ====================================================
        # RUN ACTOR
        # ====================================================

        run = client.actor(
            "compass/crawler-google-places"
        ).call(
            run_input=run_input
        )

        print(
            "ACTOR RUN COMPLETE"
        )

        dataset_id = run[
            "defaultDatasetId"
        ]

        print(
            "DATASET ID:",
            dataset_id
        )

        # ====================================================
        # GET RESULTS
        # ====================================================

        items = client.dataset(
            dataset_id
        ).list_items().items

        print(
            "TOTAL ITEMS:",
            len(items)
        )

        # ====================================================
        # PROCESS ITEMS
        # ====================================================

        for item in items:

            print("ITEM:", item)

            try:

                company_name = (
                    item.get("title")
                    or item.get("name")
                    or "Unknown Company"
                )

                website = item.get(
                    "website"
                )

                city = item.get(
                    "city",
                    "Unknown"
                )

                state = item.get(
                    "state",
                    "Unknown"
                )

                category = (
                    item.get("categoryName")
                    or data.query
                )

                # ============================================
                # DUPLICATE CHECK
                # ============================================

                existing = (
                    db.query(Company)
                    .filter(
                        Company.name
                        == company_name
                    )
                    .first()
                )

                if existing:

                    skipped += 1

                    continue

                # ============================================
                # CONTACT EXTRACTION
                # ============================================

                contacts = {

                    "emails": [],

                    "phones": [],

                    "linkedin": None,

                    "contact_page": None,

                    "address": None,
                }

                if website:

                    try:

                        contacts = (
                            extract_contacts(
                                website
                            )
                        )

                    except Exception as e:

                        print(
                            "CONTACT EXTRACTION ERROR:",
                            str(e)
                        )

                # ============================================
                # AI ICP SCORING
                # ============================================

                temp_company = type(
                    "TempCompany",
                    (),
                    {
                        "name": company_name,
                        "industry": category,
                        "website": website,
                        "city": city,
                    }
                )

                icp_score = score_company(
                    temp_company
                )

                # ============================================
                # LEAD TIERS
                # ============================================

                if icp_score >= 80:

                    tier = "Hot"

                elif icp_score >= 60:

                    tier = "Warm"

                else:

                    tier = "Cold"

                # ============================================
                # CREATE COMPANY
                # ============================================

                company = Company(

                    name=company_name[:250],

                    city=city,

                    state=state,

                    industry=category,

                    website=website,

                    email=(

                        contacts["emails"][0]

                        if contacts["emails"]

                        else None
                    ),

                    phone=(

                        contacts["phones"][0]

                        if contacts["phones"]

                        else None
                    ),

                    linkedin=contacts[
                        "linkedin"
                    ],

                    contact_page=contacts[
                        "contact_page"
                    ],

                    address=contacts[
                        "address"
                    ],

                    icp_score=icp_score,

                    calculated_tier=tier,

                    search_keyword=data.query,
                )

                db.add(company)

                inserted += 1

                # ============================================
                # RESPONSE OBJECT
                # ============================================

                results.append({

                    "name": company_name,

                    "website": website,

                    "city": city,

                    "state": state,

                    "industry": category,

                    "email": (

                        contacts["emails"][0]

                        if contacts["emails"]

                        else None
                    ),

                    "phone": (

                        contacts["phones"][0]

                        if contacts["phones"]

                        else None
                    ),

                    "linkedin":
                        contacts["linkedin"],

                    "contact_page":
                        contacts["contact_page"],

                    "address":
                        contacts["address"],

                    "icp_score":
                        icp_score,

                    "tier":
                        tier,
                })

            except Exception as e:

                print(
                    "ITEM ERROR:",
                    str(e)
                )

        # ====================================================
        # SAVE DATABASE
        # ====================================================

        db.commit()

        print(
            "DATABASE COMMIT COMPLETE"
        )

        return {

            "success": True,

            "query": data.query,

            "inserted": inserted,

            "skipped": skipped,

            "results": results,
        }

    except Exception as e:

        print(
            "MAIN ERROR:",
            str(e)
        )

        return {
            "success": False,
            "error": str(e),
        }

    finally:

        db.close()

        print(
            "========== SCRAPER FINISHED =========="
        )