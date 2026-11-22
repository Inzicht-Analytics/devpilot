from enum import Enum
class Action(str, Enum):
    READ = "read"
    PLAN = "plan"
    WRITE_CODE = "write_code"
    OPEN_PR = "open_pr"
    MERGE = "merge"
    DEPLOY = "deploy"
    MODIFY_SECRETS = "modify_secrets"

def allowed(action: Action) -> bool:
    """Fail closed: foundation cannot perform mutating actions."""
    return action in (Action.READ, Action.PLAN)
