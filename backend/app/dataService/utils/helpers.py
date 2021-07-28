import re
import sqlparse
import json

from datetime import date, datetime

from app.dataService.utils import constants


# Copied from NL4DV
def isfloat(datum):
    try:
        if datum == '' or str(datum).isspace():
            return False
        float(datum)
    except AttributeError:
        return False
    except ValueError:
        return False
    except OverflowError:
        return False
    return True


# Copied from NL4DV
def isint(datum):
    try:
        if datum == '' or str(datum).isspace():
            return False
        a = float(datum)
        b = int(a)
    except AttributeError:
        return False
    except ValueError:
        return False
    except OverflowError:
        return False
    return a == b


# Copied from NL4DV
def isdate(datum):
    try:
        if datum == '' or str(datum).isspace():
            return False, None

        for idx, regex_list in enumerate(constants.date_regexes):
            regex = re.compile(regex_list[1])
            match = regex.match(str(datum))
            if match is not None:
                dateobj = dict()
                dateobj["regex_id"] = idx
                dateobj["regex_matches"] = list(match.groups())
                return True, dateobj

    except Exception as e:
        pass

    return False, None


def get_attr_datatype_shorthand(data_types):
    # Attribute-Datatype pair
    unsorted_attr_datatype = [(attr, attr_type) for attr, attr_type in data_types.items()]

    # Since the `vis_combo` mapping keys are in a specific order [Q,N,O,T],
    # we will order the list of attributes in this order
    default_sort_order = ['Q', 'N', 'O', 'T']
    sorted_attr_datatype = [(attr, attr_type) for x in default_sort_order for (attr, attr_type) in
                            unsorted_attr_datatype if attr_type == x]

    sorted_attributes = [x[0] for x in sorted_attr_datatype]
    # e.g. ['Rotten Tomatoes Rating', 'Worldwide Gross']
    sorted_attribute_datatypes = ''.join([x[1] for x in sorted_attr_datatype])  # e.g. 'QQ'

    return sorted_attributes, sorted_attribute_datatypes


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, (date, datetime)):
            return obj.strftime("%Y/%m/%d")
        return json.JSONEncoder.default(self, obj)


# -------------------------------------New Edition---------------------------------------

def is_numeric(obj):
    attrs = ['__add__', '__sub__', '__mul__', '__truediv__', '__pow__']
    return all(hasattr(obj, attr) for attr in attrs)


# Modified from https://stackoverflow.com/a/68023076
def get_sql_identifiers(sql):
    stmt = sqlparse.parse(sql)[0]
    columns = []
    column_identifiers = []

    # get column_identifieres
    in_select = False
    for token in stmt.tokens:
        if isinstance(token, sqlparse.sql.Comment):
            continue
        if str(token).lower() == 'select':
            in_select = True
        elif in_select and token.ttype is None:
            for identifier in token.get_identifiers():
                column_identifiers.append(identifier)
            break

    # get column names
    for column_identifier in column_identifiers:
        column_name = column_identifier.get_name()
        if isinstance(column_identifier, sqlparse.sql.Function):
            column_name += '({})'.format(
                ','.join([p.get_name() for p in column_identifier.get_parameters()]))
        columns.append(column_name)

    return columns


# TODO: this function cannot distinguish between O(rdinal) and Q(uantitative)
def get_attr_type(data):
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("SQL returns should be a non-empty list.")
    if all([is_numeric(datum) for datum in data]):
        return "Q"  # Q is for Quantitive
    elif all([isdate(datum)[0] for datum in data]):
        return "T"  # T is for Time
    else:
        return "N"  # N is for Nominal


def join_data_types(data, identifiers):
    inversed_data = [list(e) for e in zip(*data)]
    data_with_type = {}
    for i, ident in enumerate(identifiers):
        data_with_type[ident] = {
            'data': inversed_data[i],
            'type': get_attr_type(inversed_data[i])
        }
    return data_with_type
