from flask import session

def is_admin() -> bool:
    """
    Return True if the current session is authenticated as an admin user.

    This matches existing usage in mqttplot.app:
      - session["is_admin"] is set True on successful admin login
      - session["admin_user"] may contain the admin username
    """
    # Primary flag set at login
    if session.get("is_admin") is True:
        return True

    # Backward compatibility / fallback (if older sessions use a different key)
    if session.get("admin") is True:
        return True

    # If you want to treat username 'admin' as admin even without flag:
    # return session.get("admin_user") == "admin"
    return False
