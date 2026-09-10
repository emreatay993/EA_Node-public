# SG Plotly HTML Mock Inputs

These files are self-contained Plotly HTML fixtures for manually testing the Sensor Data Comparison Tool HTML importer.

Regenerate them from the repo root:

```powershell
.\venv\Scripts\python.exe .\scripts\Sensor_Data_Comparison_Tool\mock_inputs\plotly_html\generate_mock_plotly_html_inputs.py
```

Manual comparison workflows:

- Load `SG_Calculations__Bladeout_Max_REF_LPT1_CF_1_58__von_Mises_MPa__main.html` as Dataset 1 and `SG_Calculations__Bladeout_Max_REF_LPT1_CF_1_58__von_Mises_MPa__compared_data.html` as Dataset 2.
- Load `SG_Calculations__Bladeout_Max_REF_LPT1_CF_1_58__von_Mises_MPa__main_and_compared_data.html` on both sides, then match `Main:` channels from one side to `Comp:` channels from the other.

The fixture set also includes raw strain, delta, percent, and mixed acceleration/LVDT/processed-channel examples. The HTML files intentionally embed Plotly JavaScript so they open without network access.
