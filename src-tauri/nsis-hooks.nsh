!macro AUTOLIQUID_KILL_PROCESS PROCESS_NAME
  DetailPrint "Encerrando ${PROCESS_NAME}, se estiver em execucao..."
  nsExec::ExecToLog 'taskkill /F /T /IM "${PROCESS_NAME}"'
!macroend

!macro AUTOLIQUID_KILL_RUNNING_APP
  !insertmacro AUTOLIQUID_KILL_PROCESS "api.exe"
  !insertmacro AUTOLIQUID_KILL_PROCESS "AutoLiquid.exe"
  !insertmacro AUTOLIQUID_KILL_PROCESS "app.exe"
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro AUTOLIQUID_KILL_RUNNING_APP
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro AUTOLIQUID_KILL_RUNNING_APP
!macroend
