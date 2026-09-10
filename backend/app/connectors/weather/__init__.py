"""Weather connector (MASTER_SPEC §2 diagram location: /connectors/weather).

Open-Meteo (free, keyless): raw-first fetch (§17), normalize into
forecast_cache (§6.4), enrich activities.weather_snapshot (§14), scheduled
every 6 hours by beat (§19).
"""
