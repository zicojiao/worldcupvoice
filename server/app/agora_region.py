def area_code_value(area: str, area_code_enum: object) -> int:
    normalized = area.strip().lower()
    mapping = {
        "cn": "AREA_CODE_CN",
        "china": "AREA_CODE_CN",
        "na": "AREA_CODE_NA",
        "north-america": "AREA_CODE_NA",
        "eu": "AREA_CODE_EU",
        "europe": "AREA_CODE_EU",
        "as": "AREA_CODE_AS",
        "asia": "AREA_CODE_AS",
        "jp": "AREA_CODE_JP",
        "japan": "AREA_CODE_JP",
        "in": "AREA_CODE_IN",
        "india": "AREA_CODE_IN",
        "global": "AREA_CODE_GLOB",
        "glob": "AREA_CODE_GLOB",
    }
    enum_name = mapping.get(normalized, "AREA_CODE_GLOB")
    return int(getattr(area_code_enum, enum_name).value)
