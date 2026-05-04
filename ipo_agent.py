import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup


IPO_URL = "https://stockanalysis.com/ipos/2026/"


def fetch_ipo_table():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    html = requests.get(IPO_URL, headers=headers, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")
    if not table:
        raise RuntimeError("IPO-taulukkoa ei löytynyt.")

    rows = []
    headers = [th.get_text(strip=True) for th in table.find_all("th")]

    for tr in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))

    return pd.DataFrame(rows)


def clean_price(value):
    if value is None:
        return None

    value = str(value).replace("$", "").replace(",", "").strip()

    try:
        return float(value)
    except ValueError:
        return None


def get_current_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="5d")
        if data.empty:
            return None
        return float(data["Close"].dropna().iloc[-1])
    except Exception:
        return None


def analyze_ipos(df):
    today = datetime.now(timezone.utc).date()
    results = []

    for _, row in df.iterrows():
        ticker = row.get("Symbol") or row.get("Ticker")
        company = row.get("Company Name") or row.get("Company")
        ipo_date_raw = row.get("IPO Date") or row.get("Date")
        ipo_price_raw = row.get("IPO Price") or row.get("Price")

        if not ticker or not ipo_date_raw:
            continue

        try:
            ipo_date = pd.to_datetime(ipo_date_raw).date()
        except Exception:
            continue

        age_days = (today - ipo_date).days

        # 1–6 kk IPO:sta
        if age_days < 30 or age_days > 180:
            continue

        ipo_price = clean_price(ipo_price_raw)
        if not ipo_price:
            continue

        current_price = get_current_price(ticker)
        if not current_price:
            continue

        change_pct = ((current_price / ipo_price) - 1) * 100

        # Dippi: vähintään -10 %
        if change_pct <= -10:
            results.append({
                "ticker": ticker,
                "company": company,
                "ipo_date": ipo_date,
                "age_days": age_days,
                "ipo_price": ipo_price,
                "current_price": current_price,
                "change_pct": change_pct
            })

    return sorted(results, key=lambda x: x["change_pct"])


def build_report(candidates):
    date = datetime.now().strftime("%Y-%m-%d")

    if not candidates:
        return f"""USA IPO Watch – {date}

Ei löytynyt tänään IPO-osakkeita, jotka täyttävät ehdot:
- IPO 30–180 päivää sitten
- laskenut vähintään 10 % IPO-hinnasta
- nykyhinta saatavilla

Tämä ei ole sijoitussuositus.
"""

    lines = [f"USA IPO Watch – {date}", ""]
    lines.append("Dipanneet IPO-osakkeet 1–6 kk ikkunassa:")
    lines.append("")

    for i, c in enumerate(candidates[:10], start=1):
        lines.append(
            f"{i}. {c['ticker']} – {c['company']}\n"
            f"   IPO date: {c['ipo_date']}\n"
            f"   IPO price: ${c['ipo_price']:.2f}\n"
            f"   Current price: ${c['current_price']:.2f}\n"
            f"   Change from IPO: {c['change_pct']:.1f}%\n"
            f"   Age: {c['age_days']} days\n"
        )

    lines.append("")
    lines.append("Huom: tämä on seulonta, ei sijoitussuositus.")
    return "\n".join(lines)


def send_email(subject, body):
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    email_to = os.environ["EMAIL_TO"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = email_to

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


def main():
    df = fetch_ipo_table()
    candidates = analyze_ipos(df)
    report = build_report(candidates)

    print(report)

    send_email(
        subject="USA IPO Watch – aamuraportti",
        body=report
    )


if __name__ == "__main__":
    main()
