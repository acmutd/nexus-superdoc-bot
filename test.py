import importlib

package_name = input("Check if Package exists: ")
if importlib.util.find_spec(package_name) is not None:
    print(package_name +" is installed")
else:
    print(package_name +" not installed")