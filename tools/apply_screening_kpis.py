"""Apply a narrow, measurement-only screening KPI patch to the Team 7 repo.

Run from the repository root:
    python tools/apply_screening_kpis.py

Guardrails: refuses to overwrite changed/unknown source layouts and is idempotent.
Review the git diff before committing.
"""
from pathlib import Path


def replace_once(content: str, old: str, new: str, filename: str, label: str) -> str:
    occurrences = content.count(old)
    if occurrences != 1:
        raise ValueError(
            f"{filename}: expected one match for {label}, found {occurrences}. "
            "Repository files may have changed; do not force this patch."
        )
    return content.replace(old, new, 1)


def make_patch(root: Path) -> None:
    agents_path = root / "agents.py"
    model_path = root / "model.py"
    agents = agents_path.read_text(encoding="utf-8")
    model = model_path.read_text(encoding="utf-8")

    marker = "'Screening|arrived_uls'"
    if marker in model:
        print("Screening KPI reporters are already present. No files changed.")
        return

    agents = replace_once(
        agents,
        "        uls_to_bypass = uls[num_uls_to_screen:]\n\n        for ul in uls_to_screen:",
        "        uls_to_bypass = uls[num_uls_to_screen:]\n\n"
        "        # Measurement only: do not change how loads are selected.\n"
        "        screen_log = self.model.daily_log['screening']\n"
        "        screen_log['arrived_uls'] += len(uls)\n"
        "        screen_log['screened_uls'] += len(uls_to_screen)\n"
        "        screen_log['bypassed_uls'] += len(uls_to_bypass)\n\n"
        "        for ul in uls_to_screen:",
        "agents.py", "screening selection counters",
    )
    agents = replace_once(
        agents,
        "        for ul in ready_uls:\n            for rti in ul.rtis:\n                self.process_rti(rti)",
        "        # ULs finishing recovery today (may differ from ULs screened today).\n"
        "        self.model.daily_log['screening']['processed_uls'] += len(ready_uls)\n\n"
        "        for ul in ready_uls:\n            for rti in ul.rtis:\n                self.process_rti(rti)",
        "agents.py", "recovery completions counter",
    )
    model = replace_once(
        model,
        "    def reset_daily_log(self):\n        self.daily_log = {\n            'movements': {",
        "    def reset_daily_log(self):\n        self.daily_log = {\n"
        "            'screening': {\n"
        "                'arrived_uls': 0,\n"
        "                'screened_uls': 0,\n"
        "                'bypassed_uls': 0,\n"
        "                'processed_uls': 0,\n"
        "            },\n"
        "            'movements': {",
        "model.py", "daily counter initialization",
    )
    model = replace_once(
        model,
        "        self.datacollector = mesa.DataCollector(model_reporters=reporters)\n",
        "        # Pooler screening counters. All quantities except rates are in ULs.\n"
        "        reporters.update({\n"
        "            'Screening|arrived_uls': lambda m: m.daily_log['screening']['arrived_uls'],\n"
        "            'Screening|screened_uls': lambda m: m.daily_log['screening']['screened_uls'],\n"
        "            'Screening|bypassed_uls': lambda m: m.daily_log['screening']['bypassed_uls'],\n"
        "            'Screening|processed_uls': lambda m: m.daily_log['screening']['processed_uls'],\n"
        "            'Screening|capacity_uls': lambda m: m.config.POOL_SCREENING_CAPACITY,\n"
        "            'Screening|utilization_pct': lambda m: (\n"
        "                100.0 * m.daily_log['screening']['screened_uls'] / m.config.POOL_SCREENING_CAPACITY\n"
        "                if m.config.POOL_SCREENING_CAPACITY > 0 else None\n"
        "            ),\n"
        "            'Screening|bypass_rate_pct': lambda m: (\n"
        "                100.0 * m.daily_log['screening']['bypassed_uls'] / m.daily_log['screening']['arrived_uls']\n"
        "                if m.daily_log['screening']['arrived_uls'] > 0 else None\n"
        "            ),\n"
        "        })\n\n"
        "        self.datacollector = mesa.DataCollector(model_reporters=reporters)\n",
        "model.py", "Mesa reporters",
    )
    model = replace_once(
        model,
        "            if self.all_orders:\n                pd.DataFrame(self.all_orders).sort_values(by=['Step', 'Issuer']).to_excel(writer, sheet_name='Orders', index=False)\n",
        "            if self.all_orders:\n                pd.DataFrame(self.all_orders).sort_values(by=['Step', 'Issuer']).to_excel(writer, sheet_name='Orders', index=False)\n\n"
        "            screening_cols = [c for c in df_wide.columns if c.startswith('Screening|')]\n"
        "            if screening_cols:\n"
        "                screening_df = df_wide[['Step', *screening_cols]].copy()\n"
        "                screening_df.columns = ['Step'] + [c.split('|', 1)[1] for c in screening_cols]\n"
        "                screening_df.to_excel(writer, sheet_name='Screening', index=False)\n",
        "model.py", "Screening Excel tab",
    )

    # Don't write either file until all patches have passed their anchor checks.
    agents_path.write_text(agents, encoding="utf-8", newline="\n")
    model_path.write_text(model, encoding="utf-8", newline="\n")
    print("Applied measurement-only screening KPIs to agents.py and model.py")
    print("Review: git diff -- agents.py model.py")


if __name__ == "__main__":
    make_patch(Path.cwd())
