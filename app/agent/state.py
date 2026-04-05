from typing import Annotated, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ConversationState(TypedDict):
    # Full conversation history — add_messages reducer appends, never overwrites
    messages: Annotated[list[BaseMessage], add_messages]

    # Session context (set once at conversation start)
    session_id: str
    cart_data: dict  # cart_id, customer_name, items, cart_total, currency, shopify_checkout_url

    # Conversation stage drives the entry-point routing on each graph invocation
    # greeting → awaiting_response → close
    stage: str

    # Intent of the latest customer message (set by detect_intent node)
    # interested | objection_price | objection_time | objection_need | end_call | neutral | unknown
    intent: str

    # How many times we've handled an objection this call
    objection_count: int

    # Discount state
    discount_offered: bool
    discount_percent: Optional[int]
    discount_code: Optional[str]

    # Call outcome — set by close node
    # recovered | declined | no_answer | voicemail | error
    outcome: Optional[str]

    # True once the close node has run
    call_ended: bool

    # Latest agent response text (extracted by the endpoint for easy return)
    agent_response: str
    
