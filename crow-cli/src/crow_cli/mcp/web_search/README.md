# `web_search`

async def web_search(query: str, limit: int = 5) -> str:
    """## Search Tool Instructions
    **Search the internet. USE THIS LIBERALLY.**
    If you are:
    - Uncertain about the user's query
    - About to make something up
    - Suspecting the USER is making something up
    - Working with a library/API you haven't seen recently
    - Debugging an error message you don't recognize
    Then SEARCH. Search in parallel (4-5 max). Search before you hallucinate.
    SEARCH INTERNET AS MUCH AS FILESYSTEM! I PITY THE FOOL WHO DON'T USE WEB SEARCH!
    This is not a fallback tool. This is a primary tool. Good developers search the internet constantly. So should you.
    **Tips for better results:**
    - To search a specific website, add the site name to your query (e.g., "python async stackoverflow" or "react hooks site:reactjs.org")
    - To find recent results, add timeframes to your query (e.g., "rust 2024", "next.js news this week")
    - If a snippet looks promising but is cut off, use the fetch tool to pull down the full page
    **Arguments:**
    - `query: str` - Your search query for the search engine
    - `limit: int = 5` - Optional, control the number of results
    **Example use:**
    result: str = search(query="How to make key lime pie")
