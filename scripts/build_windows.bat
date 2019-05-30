
@rem Install python and make sure it's in the path.
choco install python3
set PATH="C:\Program Files\Python37;C:\Program Files\Python37\Scripts;%PATH%"

@rem Install requirements.
pip3 install -r dev-requirements.txt capstone

@rem Build the pyocd executable.
pyinstaller -F pyocd.spec


