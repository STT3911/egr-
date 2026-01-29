@echo off
REM Скрипт для загрузки данных ГРП из списка УНП в файле ngrm_list.txt (Windows)

echo.
echo ===================================================================
echo   ЗАГРУЗКА ДАННЫХ ГРП ИЗ СПИСКА УНП В ngrm_list.txt
echo ===================================================================
echo.
echo Этот скрипт читает УНП из файла ngrm_list.txt
echo и загружает данные о налогоплательщиках из GRP API.
echo.

python fetch-grp-from-ngrn-list.py

echo.
pause