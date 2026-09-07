"""Write the synthetic banking book to CSV so the dataset can be opened without the app."""
from pathlib import Path

from data.generate import events, generate

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    df = generate()
    df.to_csv(HERE / "banking_book.csv")
    events().to_csv(HERE / "events.csv", index=False)
    print("wrote", len(df), "rows")
