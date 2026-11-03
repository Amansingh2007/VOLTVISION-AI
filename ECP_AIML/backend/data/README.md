# Dataset setup

No dataset was included with the project. Add a real dataset as `electricity.csv`.

Minimum required columns:
```csv
timestamp,consumption_kwh
2010-01-01 00:00:00,1.24
2010-01-01 01:00:00,0.98
```

The example rows above only show the format; they are not real measurements.

Recommended starting point: UCI Machine Learning Repository, **Individual Household Electric Power Consumption** dataset. It contains household power readings at minute-level intervals. When preparing it, convert active power (kW) and timestamps into interval energy (kWh), handle missing values, and resample into hourly/daily totals. Do not treat instantaneous kW readings as kWh without conversion.

Dataset source: https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption
