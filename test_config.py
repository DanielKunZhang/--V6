#!/usr/bin/env python3
"""测试配置文件加载"""

import yaml

def test_config():
    config_path = 'config_option_writer.yaml'
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    print("✅ 配置文件加载成功")
    print(f"配置文件结构键名: {list(config.keys())}")
    
    if 'sell_put' in config:
        print(f"\n📊 sell_put 配置:")
        sell_put_config = config['sell_put']
        print(f"  键名: {list(sell_put_config.keys())}")
        
        if 'expiry_days_min' in sell_put_config:
            print(f"  expiry_days_min: {sell_put_config['expiry_days_min']} (类型: {type(sell_put_config['expiry_days_min'])})")
        else:
            print(f"  ❌ expiry_days_min 不存在!")
            
        if 'expiry_days_max' in sell_put_config:
            print(f"  expiry_days_max: {sell_put_config['expiry_days_max']} (类型: {type(sell_put_config['expiry_days_max'])})")
        else:
            print(f"  ❌ expiry_days_max 不存在!")
    else:
        print(f"❌ sell_put 配置不存在!")

if __name__ == "__main__":
    test_config()