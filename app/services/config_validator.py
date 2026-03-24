"""Config validator — structural and cross-reference validation for service configs.

Validates that a config dict is well-formed before saving to the database.
Semantic validation (e.g. sku_groups values exist in retail_prices) is
deferred to a future phase when the retail_prices table is available.
"""

from app.services.sub_dimensions import get_sub_dimension_parser

VALID_QUANTITY_MODELS = {"instances_x_hours", "per_meter"}


def validate_config(config: dict) -> tuple[list[str], list[str]]:
    """Validate a service config dict.

    Returns:
        (errors, warnings) — lists of strings.
        errors: must be fixed before saving.
        warnings: informational, saving is allowed.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- quantity_model ---
    qm = config.get("quantity_model")
    if qm and qm not in VALID_QUANTITY_MODELS:
        errors.append(
            f"quantity_model '{qm}' is not valid. Must be one of: {sorted(VALID_QUANTITY_MODELS)}"
        )

    # --- defaults ---
    defaults = config.get("defaults")
    if defaults is not None:
        if not isinstance(defaults, dict):
            errors.append("defaults must be a JSON object")
        else:
            if "selections" in defaults and not isinstance(defaults["selections"], dict):
                errors.append("defaults.selections must be a JSON object")
            if "sub_selections" in defaults and not isinstance(defaults["sub_selections"], dict):
                errors.append("defaults.sub_selections must be a JSON object")
            hours = defaults.get("hours_per_month")
            if hours is not None and (not isinstance(hours, (int, float)) or hours <= 0):
                errors.append("defaults.hours_per_month must be a positive number")

    # --- sub_dimensions ---
    sub_dims = config.get("sub_dimensions")
    if sub_dims is not None:
        if not isinstance(sub_dims, dict):
            errors.append("sub_dimensions must be a JSON object")
        else:
            parser_name = sub_dims.get("parser")
            if parser_name:
                # Derive a fake service_name to check parser availability
                # Parser registry is keyed by service_name; use parser field directly
                if not _parser_exists(parser_name):
                    warnings.append(
                        f"sub_dimensions.parser '{parser_name}' is not registered. "
                        "The parser must be added to app/services/sub_dimensions.py."
                    )

            dimensions = sub_dims.get("dimensions", [])
            if not isinstance(dimensions, list):
                errors.append("sub_dimensions.dimensions must be a list")
            else:
                known_fields = {d.get("field") for d in dimensions if isinstance(d, dict)}
                for dim in dimensions:
                    if not isinstance(dim, dict):
                        errors.append("Each entry in sub_dimensions.dimensions must be an object")
                        continue
                    if "field" not in dim:
                        errors.append("Each sub_dimension entry must have a 'field' key")
                    if "label" not in dim:
                        warnings.append(
                            f"sub_dimension '{dim.get('field', '?')}' has no 'label'"
                        )

                # Cross-check static_subs and hidden_subs
                for list_name in ("static_subs", "hidden_subs"):
                    vals = config.get(list_name, [])
                    if not isinstance(vals, list):
                        errors.append(f"{list_name} must be a list")
                        continue
                    for v in vals:
                        if v not in known_fields:
                            errors.append(
                                f"{list_name} references '{v}' which is not in "
                                "sub_dimensions.dimensions"
                            )

    # --- sku_groups ---
    sku_groups = config.get("sku_groups")
    if sku_groups is not None:
        if not isinstance(sku_groups, dict):
            errors.append("sku_groups must be a JSON object")
        else:
            for group_name, members in sku_groups.items():
                if not isinstance(members, list):
                    errors.append(f"sku_groups['{group_name}'] must be a list of strings")
                elif not all(isinstance(m, str) for m in members):
                    errors.append(f"sku_groups['{group_name}'] must contain only strings")

    # --- dimension_labels ---
    dim_labels = config.get("dimension_labels")
    if dim_labels is not None and not isinstance(dim_labels, dict):
        errors.append("dimension_labels must be a JSON object")

    # --- hidden_dimensions ---
    hidden = config.get("hidden_dimensions")
    if hidden is not None and not isinstance(hidden, list):
        errors.append("hidden_dimensions must be a list")

    # --- excluded_products ---
    excluded = config.get("excluded_products")
    if excluded is not None and not isinstance(excluded, list):
        errors.append("excluded_products must be a list")

    # --- hidden_meters ---
    hidden_meters = config.get("hidden_meters")
    if hidden_meters is not None:
        if not isinstance(hidden_meters, list):
            errors.append("hidden_meters must be a list")
        elif not all(isinstance(m, str) for m in hidden_meters):
            errors.append("hidden_meters must contain only strings")

    # --- warnings for missing recommended fields ---
    if not config.get("quantity_model"):
        warnings.append("quantity_model is not set; defaults to 'instances_x_hours' at runtime")
    if not config.get("defaults"):
        warnings.append("defaults is not set; users will see no pre-selected values")

    return errors, warnings


def _parser_exists(parser_name: str) -> bool:
    """Check if a sub-dimension parser is registered."""
    # get_sub_dimension_parser accepts service_name, not parser name.
    # We can't directly look up by parser field name without refactoring.
    # For now, try known parser names via service name convention.
    # Future: expose a parser registry lookup function.
    known_parsers = {"vm_product_parser", "app_service_parser"}
    return parser_name in known_parsers
