# Global variables
# ##############################
import os

test = os.getcwd()

_current_dir = os.path.dirname(os.path.abspath(__file__))

# data folder
DATA_FOLDER = os.path.join(_current_dir, '../data/')
SPIDER_FOLDER = os.path.join(DATA_FOLDER, "dataset/spider")
NVBENCH_FOLDER = os.path.join(DATA_FOLDER, "dataset/nvBench")

# model folder
MODEL_FOLDER = os.path.join(DATA_FOLDER, 'model')
SMBOP_PATH = os.path.join(DATA_FOLDER, 'model/smbop.tar.gz')
SMBOP_FOLDER = os.path.join(MODEL_FOLDER, "SmBop")

#################### SQL parser variables
##### adopted from https://github.com/taoyds/spider/blob/88c04b7ee43a4cc58984369de7d8196f55a84fbf/process_sql.py
CLAUSE_KEYWORDS = ('select', 'from', 'where', 'group', 'order', 'limit', 'intersect', 'union', 'except')
JOIN_KEYWORDS = ('join', 'on', 'as')

WHERE_OPS = ('not', 'between', '=', '>', '<', '>=', '<=', '!=', 'in', 'like', 'is', 'exists')
UNIT_OPS = ('none', '-', '+', "*", '/')
AGG_OPS = ('none', 'max', 'min', 'count', 'sum', 'avg')
TABLE_TYPE = {
    'sql': "sql",
    'table_unit': "table_unit",
}

COND_OPS = ('and', 'or')
SQL_OPS = ('intersect', 'union', 'except')
ORDER_OPS = ('desc', 'asc')