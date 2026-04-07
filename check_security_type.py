from futu import *
import inspect

# 查看SecurityType的所有属性
print("SecurityType attributes:")
for name, value in inspect.getmembers(SecurityType):
    if not name.startswith('_'):
        print(f"  {name} = {value}")

# 查看Market的所有属性  
print("\nMarket attributes:")
for name, value in inspect.getmembers(Market):
    if not name.startswith('_'):
        print(f"  {name} = {value}")