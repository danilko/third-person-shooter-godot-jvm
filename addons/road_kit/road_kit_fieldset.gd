@tool
extends RefCounted
## A field table (road_kit_fields.gd) as live, inspector-visible, scene-saved properties.
## Storage is one Dictionary per table; properties are exposed as `<prefix><field>`.

static func defaults(table: Array) -> Dictionary:
	var d := {}
	for row in table:
		d[row[0]] = row[2]
	return d

static func coerce(row: Array, v):
	match row[1]:
		"i": return int(v)
		"f": return float(v)
		"b": return bool(v)
		"s": return "" if v == null else str(v)
		"e": return v if row[3].has(v) else row[2]
	return v

static func property_list(table: Array, prefix: String, group: String, skip: Array = []) -> Array[Dictionary]:
	var out: Array[Dictionary] = [{"name": group, "type": TYPE_NIL, "usage": PROPERTY_USAGE_GROUP, "hint_string": prefix}]
	for row in table:
		if skip.has(row[0]):
			continue
		var p := {"name": prefix + row[0], "usage": PROPERTY_USAGE_DEFAULT}
		match row[1]:
			"i": p["type"] = TYPE_INT
			"f": p["type"] = TYPE_FLOAT
			"b": p["type"] = TYPE_BOOL
			"s": p["type"] = TYPE_STRING
			"e":
				p["type"] = TYPE_STRING
				p["hint"] = PROPERTY_HINT_ENUM
				p["hint_string"] = ",".join(row[3])
		out.append(p)
	return out

static func row_of(table: Array, field: String) -> Array:
	for row in table:
		if row[0] == field:
			return row
	return []

## The `to_dict` rule: every value that differs from its default, plus `always`.
static func to_dict(table: Array, values: Dictionary, always: Array = []) -> Dictionary:
	var d := {}
	for row in table:
		var v = values.get(row[0], row[2])
		if always.has(row[0]) or v != row[2]:
			d[row[0]] = snappedf(v, 0.000001) if row[1] == "f" else v
	return d

static func from_dict(table: Array, d: Dictionary) -> Dictionary:
	var out := defaults(table)
	for row in table:
		if d.has(row[0]):
			out[row[0]] = coerce(row, d[row[0]])
	return out
