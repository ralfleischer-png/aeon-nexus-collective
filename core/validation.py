def validate_proposal(payload: dict) -> dict:
    errors = []

    title = payload.get("title")
    description = payload.get("description")
    content = payload.get("content")

    if not isinstance(title, str) or not title.strip():
        errors.append("title must be a non-empty string")
    if not isinstance(description, str):
        errors.append("description must be a string")
    if content is None:
        errors.append("content is required")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_vote(payload: dict) -> dict:
    errors = []
    vote = payload.get("vote")
    if vote not in ("FOR", "AGAINST", "ABSTAIN"):
        errors.append("vote must be one of FOR, AGAINST, ABSTAIN")
    return {"valid": len(errors) == 0, "errors": errors}
