def get_cfg_value(cfg):
    value = cfg.get("a", {}).get("b", {}).get("c")
    return value
