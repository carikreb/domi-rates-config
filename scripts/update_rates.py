import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPREADS_FILE = ROOT / "spreads_config.json"
RATES_FILE = ROOT / "rates_config.json"

# Endpoint ufficiali SDMX-JSON della Banca Centrale Europea (BCE)
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
SERIES = {
    "euribor_1m": f"{ECB_BASE}/FM/M.U2.EUR.RT.MM.EURIBOR1MD_.HSTA?lastNObservations=1&format=jsondata",
    "euribor_3m": f"{ECB_BASE}/FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA?lastNObservations=1&format=jsondata",
    "yield_10": f"{ECB_BASE}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=1&format=jsondata",
    "yield_15": f"{ECB_BASE}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_15Y?lastNObservations=1&format=jsondata",
    "yield_20": f"{ECB_BASE}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_20Y?lastNObservations=1&format=jsondata",
    "yield_25": f"{ECB_BASE}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_25Y?lastNObservations=1&format=jsondata",
    "yield_30": f"{ECB_BASE}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_30Y?lastNObservations=1&format=jsondata",
}


def fetch_ecb_rate_e6(url: str) -> int:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "DomiRatesBot/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    series_map = payload["dataSets"][0]["series"]
    first_series = next(iter(series_map.values()))
    observations = first_series["observations"]
    latest_key = sorted(observations.keys(), key=int)[-1]
    rate_percent = float(observations[latest_key][0])

    # Validazione di sicurezza: scarta valori fuori range (-1% .. +20%)
    if not (-1.0 <= rate_percent <= 20.0):
        raise ValueError(f"Tasso fuori range plausibile: {rate_percent}%")

    # Conversione in milionesimi (e6): 1% = 10.000
    return int(round(rate_percent * 10_000))


def main() -> None:
    spreads = json.loads(SPREADS_FILE.read_text(encoding="utf-8"))
    current = json.loads(RATES_FILE.read_text(encoding="utf-8"))
    swap_offset = int(spreads.get("irsSwapSpreadOffsetE6", 0))

    fetched: dict[str, int] = {}
    for key, url in SERIES.items():
        try:
            fetched[key] = fetch_ecb_rate_e6(url)
            print(f"[OK] {key}: {fetched[key]} e6")
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
            print(f"[WARN] Errore su {key} ({exc}), mantengo valore precedente.")

    new_eurirs = {
        "10": fetched["yield_10"] + swap_offset if "yield_10" in fetched else current["eurirs"]["10"],
        "15": fetched["yield_15"] + swap_offset if "yield_15" in fetched else current["eurirs"]["15"],
        "20": fetched["yield_20"] + swap_offset if "yield_20" in fetched else current["eurirs"]["20"],
        "25": fetched["yield_25"] + swap_offset if "yield_25" in fetched else current["eurirs"]["25"],
        "30": fetched["yield_30"] + swap_offset if "yield_30" in fetched else current["eurirs"]["30"],
    }
    new_euribor = {
        "1m": fetched.get("euribor_1m", current["euribor"]["1m"]),
        "3m": fetched.get("euribor_3m", current["euribor"]["3m"]),
    }

    now = datetime.now(timezone.utc)
    updated = {
        "schemaVersion": spreads["schemaVersion"],
        "version": now.strftime("%Y-%m-%d"),
        "publishedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "BCE (European Central Bank Data Portal) + Benchmark Domì",
        "eurirs": new_eurirs,
        "euribor": new_euribor,
        "spreadsByLtv": spreads["spreadsByLtv"],
        "greenDiscount": spreads["greenDiscount"],
        "minAppVersion": spreads["minAppVersion"],
    }

    # Scrive il file solo se i dati economici sono effettivamente cambiati
    comparable_old = {k: v for k, v in current.items() if k not in ("version", "publishedAt")}
    comparable_new = {k: v for k, v in updated.items() if k not in ("version", "publishedAt")}

    if comparable_old == comparable_new:
        print("Nessuna variazione nei tassi rispetto all'ultimo aggiornamento.")
        return

    RATES_FILE.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Aggiornato rates_config.json alla versione {updated['version']}.")


if __name__ == "__main__":
    main()
