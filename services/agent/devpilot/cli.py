from devpilot.policy import Action, allowed
def main():
    for action in Action:
        print(f"{action.value}: {'allowed' if allowed(action) else 'blocked'}")
if __name__ == "__main__":
    main()
