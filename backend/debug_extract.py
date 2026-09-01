"""Debug person extraction from Serper search."""
from services.research_provider import research_router
from services.decision_maker_discovery import extract_person_candidates, _fuzzy_company_match

res = research_router.search('"Bharat Forge Ltd" "Quality Head" Pune', num_results=5)
print('Live Serper Results Count:', len(res['results']))
for r in res['results']:
    title_safe = r['title'].encode('ascii', 'replace').decode('ascii')
    snippet_safe = r['snippet'].encode('ascii', 'replace').decode('ascii')
    print('\nTITLE:', title_safe)
    print('URL:', r['url'])
    print('SNIPPET:', snippet_safe)
    match_score = _fuzzy_company_match(r['title'] + ' ' + r['snippet'], 'Bharat Forge Ltd')
    print('COMPANY MATCH SCORE:', match_score)

cands = extract_person_candidates(res['results'], 'Bharat Forge Ltd')
print('\nEXTRACTED CANDIDATES:', len(cands))
for c in cands:
    print(f"  • Candidate: {c['candidate_name']} | Title: {c['candidate_title']} | URL: {c['evidence_url']}")
