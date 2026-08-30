import os

from app.data.database import Base, SessionLocal, engine
from app.data.seed import reset_demo_data

CONFIRMATION_VARIABLE = "CONFIRM_DEMO_DATA_RESET"
CONFIRMATION_VALUE = "reset-fonio-demo-data"


def main() -> None:
    if os.getenv(CONFIRMATION_VARIABLE) != CONFIRMATION_VALUE:
        raise SystemExit(
            f"Refusing to reset data. Set {CONFIRMATION_VARIABLE}="
            f"{CONFIRMATION_VALUE} to confirm."
        )
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        reset_demo_data(session)
    print("Fonio demo data reset completed.")


if __name__ == "__main__":
    main()
