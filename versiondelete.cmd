@echo off
set /p "tagname=Enter the version to delete: "

:: Delete local tag
git tag -d %tagname%

echo.
echo Deleting the version from remote origin...

:: Delete remote tag 
git push origin :%tagname%

echo.
echo Process Completed!

pause