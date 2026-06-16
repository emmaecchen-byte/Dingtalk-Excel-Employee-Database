"""Application startup seed — delegates to scripts/seed_demo_data.py."""


def seed_database(db) -> None:
    from scripts.seed_demo_data import seed_demo_data

    seed_demo_data(db)
