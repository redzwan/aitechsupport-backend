"""Grant (or revoke) platform-admin on a user by email.

Usage:
    python scripts/make_admin.py <email>            # grant
    python scripts/make_admin.py <email> --revoke   # revoke
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/make_admin.py <email> [--revoke]")
        sys.exit(1)
    email = sys.argv[1]
    grant = "--revoke" not in sys.argv[2:]

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"No user with email {email}")
            sys.exit(1)
        user.is_platform_admin = grant
        db.commit()
        print(f"{email} platform_admin = {grant} (id={user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
