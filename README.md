{
  "^SAM_HANGINGUPB_Start_.*\\.complete$": {
    "job_name": "CAL_SERVICES_UPDATE_STAGE_DEVL1",
    "command": "sendevent -E FORCE_STARTJOB -j GV7#SAM#cmd#CAL_SERVICES_UPDATE_STAGE_DEVL1"
  },

  "^SAM_FICC_Start_.*\\.complete$": {
    "job_name": "FICC_GENCOST_ADHOC_DEVL1",
    "command": "sendevent -E FORCE_STARTJOB -j GV7#SAM#box#FICC_GENCOST_ADHOC_DEVL1"
  },

  "^SAM_GL_Extract_.*\\.complete$": {
    "job_name": "GLT_SEC_GL_ADHOC_DEVL1",
    "command": "sendevent -E FORCE_STARTJOB -j GV7#SAM#box#GLT_SEC_GL_ADHOC_DEVL1"
  },

  "^SAM_GL_Publish_.*\\.complete$": {
    "job_name": "GLT_SEC_GL_START_ADHOC_DEVL1",
    "command": "sendevent -E JOB_OFFHOLD -j GV7#SAM#cmd#GLT_SEC_GL_START_ADHOC_DEVL1"
  },

  "^SAM_GLCLOSE_SCD_.*\\.complete$": {
    "job_name": "SAM_GLCLOSE_SCD_ADHOC_DEVL1",
    "command": "sendevent -E FORCE_STARTJOB -j GV7#SAM#box#SAM_GLCLOSE_SCD_ADHOC_DEVL1"
  },

  "^SAM_EYTAXBUS_VEND_.*\\.complete$": {
    "job_name": "EYTAXBUS_VEND_ADHOC_DEVL1",
    "command": "sendevent -E FORCE_STARTJOB -j GV7#SAM#box#EYTAXBUS_VEND_ADHOC_DEVL1"
  }
}