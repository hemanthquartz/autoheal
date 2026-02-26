{
  "description": "ECM Blackline Daily Box Migration from AutoSys",
  "dataset_event": "producer",
  "start_date": "2026-02-13",
  "email": ["gv7devl@fanniemae.com"],
  "catchup": false,
  "default_args": {
    "depends_on_past": false,
    "email_on_failure": true,
    "email_on_retry": false,
    "retries": 1,
    "retry_delay": { "minutes": 5 }
  },
  "tags": ["env:DEVL6", "app:ecm", "asset:GV7"],
  "environment": "DEVL6",
  "tasks": [

    {
      "task_name": "GV7_ECM_cmd_ECM_BLSL_GLT_REC_G_D_DEVL6",
      "execution_type": "local",
      "task_type": "python",
      "command": "python scwrap.py -w ECM_SCD_WDC -p ECM_BLSL_GLT_REC_G_D -j ECM_BLSL_GLT_REC_G_D -d GV7_ECM_SCD_WDC_ACTG_PRD_DEVL6",
      "condition": "",
      "description": "Run ECM_BLSL_GLT_REC_G_D job",
      "machine": "MF_ECM_SCD_VM",
      "retries": 1
    },

    {
      "task_name": "GV7_ECM_cmd_ECM_BLSL_GLT_CG_D_DEVL6",
      "execution_type": "local",
      "task_type": "python",
      "command": "python scwrap.py -w ECM_SCD_WDC -p ECM_BLSL_GLT_CG_D -j ECM_BLSL_GLT_CG_D -d GV7_ECM_SCD_WDC_ACTG_PRD_DEVL6",
      "condition": "s(GV7_ECM_cmd_ECM_BLSL_GLT_REC_G_D_DEVL6)",
      "description": "Run ECM_BLSL_GLT_CG_D job",
      "machine": "MF_ECM_SCD_VM",
      "retries": 1
    },

    {
      "task_name": "GV7_ECM_cmd_ECM_BLSL_GAAP_CMP_D_DEVL6",
      "execution_type": "local",
      "task_type": "python",
      "command": "python scwrap.py -w ECM_SCD_WDC -p ECM_BLSL_GAAP_CMP_D -j ECM_BLSL_GAAP_CMP_D -d GV7_ECM_SCD_WDC_ACTG_PRD_DEVL6",
      "condition": "s(GV7_ECM_cmd_ECM_BLSL_GLT_CG_D_DEVL6)",
      "description": "Run ECM_BLSL_GAAP_CMP_D job",
      "machine": "MF_ECM_SCD_VM",
      "retries": 1
    },

    {
      "task_name": "GV7_ECM_cmd_ECM_BLSL_GLT_REC_T_D_DEVL6",
      "execution_type": "local",
      "task_type": "python",
      "command": "python scwrap.py -w ECM_SCD_WDC -p ECM_BLSL_GLT_REC_T_D -j ECM_BLSL_GLT_REC_T_D -d GV7_ECM_SCD_WDC_ACTG_PRD_DEVL6",
      "condition": "s(GV7_ECM_cmd_ECM_BLSL_GAAP_CMP_D_DEVL6)",
      "description": "Run ECM_BLSL_GLT_REC_T_D job",
      "machine": "MF_ECM_SCD_VM",
      "retries": 1
    },

    {
      "task_name": "GV7_ECM_cmd_ECM_BLSL_GLT_CT_D_DEVL6",
      "execution_type": "local",
      "task_type": "python",
      "command": "python scwrap.py -w ECM_SCD_WDC -p ECM_BLSL_GLT_CT_D -j ECM_BLSL_GLT_CT_D -d GV7_ECM_SCD_WDC_ACTG_PRD_DEVL6",
      "condition": "s(GV7_ECM_cmd_ECM_BLSL_GLT_REC_T_D_DEVL6)",
      "description": "Run ECM_BLSL_GLT_CT_D job",
      "machine": "MF_ECM_SCD_VM",
      "retries": 1
    },

    {
      "task_name": "GV7_ECM_cmd_ECM_BLSL_TAX_CMP_D_DEVL6",
      "execution_type": "local",
      "task_type": "python",
      "command": "python scwrap.py -w ECM_SCD_WDC -p ECM_BLSL_TAX_CMP_D -j ECM_BLSL_TAX_CMP_D -d GV7_ECM_SCD_WDC_ACTG_PRD_DEVL6",
      "condition": "s(GV7_ECM_cmd_ECM_BLSL_GLT_CT_D_DEVL6)",
      "description": "Run ECM_BLSL_TAX_CMP_D job",
      "machine": "MF_ECM_SCD_VM",
      "retries": 1
    }

  ]
}



{
  "description": "ECM Daily Blackline Move Files Box",
  "dataset_event": "producer",
  "start_date": "2026-02-13",
  "environment": "DEVL6",
  "tasks": [

    {
      "task_name": "GV7_ECM_cmd_ECM_MOVE_BLACKLINE_DAILY_FILES_DEVL6",
      "execution_type": "local",
      "task_type": "bash",
      "command": "python moveFile.py InOut/ECM/Blackline/TEMP InOut/ECM/Blackline/Out",
      "condition": "",
      "description": "Moves blackline daily files from temp to out",
      "machine": "MF_ECM_SCD_VM",
      "retries": 1
    }

  ]
}
