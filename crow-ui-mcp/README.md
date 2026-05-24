


```python

from fastmcp import FastMCP

from fastmcp.tools import ArgTransform

mcp = FastMCP("MyServer")

def search_records(query: str, user_id: str):

    return f"Searching {query} for user {user_id}"

# Transform the tool before exposing it to the LLM

mcp.add_tool(

    search_records,

    name="search_my_records",

    transform_args={

        "user_id": ArgTransform(

            hide=True, 

            default_factory=get_current_user_id 

            # Alternatively, use a static default: default="user_123"

        )

    }

)
```
