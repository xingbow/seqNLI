import os
import sys
import re
import json
import numpy as np
import pandas as pd
import math

from sentence_transformers import SentenceTransformer, util
from mlxtend.frequent_patterns import fpmax
from sklearn.metrics.pairwise import cosine_similarity

try:
    import globalVariable as GV
    from utils.processSQL import process_sql, decode_sql
except ImportError:
    import app.dataService.globalVariable as GV
    from app.dataService.utils.processSQL import process_sql, decode_sql

test_topic = "employee_hire_evaluation"
test_table_cols = ['employee: employee id',
                   'employee: name',
                   'employee: age',
                   'employee: city',
                   'shop: shop id',
                   'shop: name',
                   'shop: location',
                   'shop: district',
                   'shop: number products',
                   'shop: manager name',
                   'hiring: shop id',
                   'hiring: employee id',
                   'hiring: start from',
                   'hiring: is full time',
                   'evaluation: employee id',
                   'evaluation: year awarded',
                   'evaluation: bonus',
                   'employee: *',
                   'shop: *',
                   'hiring: *',
                   'evaluation: *']


class queryRecommender(object):
    def __init__(self, search_cols, topic_sim_th=0.4, item_sim=0.4, alpha=0.9, beta=0.5,
                 groupby_th=0.4, agg_th=0.4, sim=0.7,
                 ref_db_meta_path=os.path.join(GV.SPIDER_FOLDER, "train_spider.json")):
        self.GV = GV
        self.model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
        # self.model = SentenceTransformer('paraphrase-MiniLM-L12-v2')

        self.db_schema, self.db_names, self.tables = process_sql.get_schemas_from_json(
            os.path.join(GV.SPIDER_FOLDER, "tables.json"))
        self.db_new_names = [re.sub(r'[0-9]+', '', n.replace("_", " ")).strip().lower() for n in
                             self.db_names]

        # --- parameter setting
        self.topic_sim_th = topic_sim_th
        self.item_sim = item_sim
        self.groupby_th = groupby_th
        self.agg_th = agg_th
        self.sim = sim
        self.alpha = alpha  # relevance decay for seqeuential query
        self.beta = beta
        # --- reference database
        with open(ref_db_meta_path, "r") as f:
            ref_db_data = pd.DataFrame(json.load(f))
        self.dataset = ref_db_data
        # --- target table to search
        self.search_cols = search_cols

    def cal_cosine_sim(self, sen0, sen1):
        """
        - calculate cosine similairty between sen0 and sen1
        - INPUT:
          - sen0: list of str or single str
          - sen1: list of str or single str
        - OUTPUT:
          - cosine similarity between sen0 and sen1
        """
        embedd0 = self.model.encode(sen0, convert_to_tensor=True)
        embedd1 = self.model.encode(sen1, convert_to_tensor=True)
        cosine_scores = util.pytorch_cos_sim(embedd0, embedd1).cpu().numpy()
        return cosine_scores

    def search_sim_dbs(self, topic):
        sim_scores = self.cal_cosine_sim(topic, self.db_new_names)[0]
        related_db_names = [self.db_names[i] for i in np.where(sim_scores > self.topic_sim_th)[0]]
        row_sims = []
        rowids = []
        for rowid, row in self.dataset.iterrows():
            if row["db_id"] in related_db_names:
                rowids.append(rowid)
                # entity in `select` clause
                select_decoded = decode_sql.decode_select(row["sql"], self.tables[row["db_id"]])
                select_ents = decode_sql.extract_select_names(select_decoded)
                # calculate similarity between `select` items and `select` cols
                row_sim = self.cal_cosine_sim(self.search_cols, select_ents)
                row_sims.append(np.max(row_sim, axis=1))
        db_df_bin = pd.DataFrame(np.where(np.array(row_sims) > self.item_sim, 1, 0),
                                 columns=self.search_cols)
        self.ref_db = (self.dataset.loc[rowids]).reset_index(drop=True)
        sim_sum = [sum(db_df_bin[col]) for col in db_df_bin.columns]
        db_df_bin = db_df_bin[db_df_bin.columns[(-np.array(sim_sum)).argsort()]]
        return db_df_bin

    def get_freq_combo(self, df, filter_set=set([]), support=None):
        """
        - input: dataframe (m * n) => binary values
        - output: frequent combo => columns: support, itemsets, itemlen
        """
        if support is None:
            support = self.item_sim
        freq_combo = fpmax(df, min_support=support, use_colnames=True)
        freq_combo["itemlen"] = freq_combo["itemsets"].apply(len)
        # filter regarding to condition
        if len(filter_set) > 0:
            freq_combo = freq_combo.iloc[
                [rowid for rowid, row in enumerate(freq_combo["itemsets"]) if
                 row.issubset(filter_set) == False]]
        freq_combo = freq_combo.sort_values(["itemlen", "support"], ascending=False).reset_index(
            drop=True)
        return freq_combo

    def get_opts(self, df, cols, groupby_contexts=[], agg_contexts=[]):
        """
        recommend  `groupby` & `agg_opt` items
        `agg_opt` items: `avg`, `min`, `max`, `count`, `sum`
        - input: binary feature vectors (size: db_col_num * input_col_num) for input table cols
        - output: `groupby` cols ([col1, col2]), `agg_opt` lists ([{"opt": "col"}, {}])
        """
        agg_opts = ['max', 'min', 'count', 'sum', 'avg']
        groupby_sugg = []
        agg_sugg = []

        # `groupby` and `agg` contexts 
        groupby_contexts = np.hstack(
            [['shop: manager name'], [], ["shop: district", "shop: location"]])
        ##############################
        # calculate `groupby` context relecance (between remaining cols and groupby contexts)
        df_col_diff = df.columns.difference(set(groupby_contexts))
        groupby_c_sim = np.max(self.cal_cosine_sim(groupby_contexts, df_col_diff), axis=0)
        # print(f"groupby_c_sim: {groupby_c_sim}", groupby_c_sim.shape)
        df_col_diff = df_col_diff[(-groupby_c_sim).argsort()]
        groupby_c_sim = groupby_c_sim[(-groupby_c_sim).argsort()]
        gb_sugg_context = [gb for gb in list(df_col_diff[groupby_c_sim > self.sim]) if
                           "*" not in gb]  # handle (table_name: *) situations
        # print(f"gb_sugg_context: {gb_sugg_context}")
        # print("*"*10)
        ##############################
        agg_contexts = [{}, {}, {"count": ["evalution: *", 'shop: number products']}]
        # print(f"groupby_contexts = {groupby_contexts}, agg_contexts = {agg_contexts}")

        for _, col in enumerate(cols):
            col_mul = np.prod(df[col], axis=1)
            col_mul_idx = np.where(col_mul == 1)[0]
            all_groupby_names = []
            agg_list = []
            for rowid, row in self.ref_db.iloc[col_mul_idx].iterrows():
                db_id = row["db_id"]
                table = self.tables[db_id]
                sql = row["sql"]
                # extract `groupby` entities
                groupby_decoded = decode_sql.decode_groupby(sql["groupBy"], table)
                groupby_names = decode_sql.extract_groupby_names(groupby_decoded)
                # extract `agg` operations
                select_decoded = decode_sql.decode_select(sql, table)
                agg_dict = decode_sql.extract_agg_opts(select_decoded)
                agg_list.append(agg_dict)
                if len(groupby_names) > 0:
                    all_groupby_names.append(groupby_names)
            # `groupby` entity suggestion
            # TODO: Thresholds `groupby` confidence support and similarity
            # TODO: Whether context/history `groupby` opts should be included in the next `groupby` opt? - Current: remove context/history opt
            ################################################################
            # calculate db `groupby` relevance
            gb_sugg = []
            if len(col_mul_idx) > 0:
                if len(all_groupby_names) / len(
                        col_mul_idx) > self.groupby_th:  # confidence thresholds
                    # print(all_groupby_names)
                    groupby_sim = np.max(
                        self.cal_cosine_sim(np.concatenate(all_groupby_names), df.columns), axis=0)
                    groupby_cols = df.columns[(-groupby_sim).argsort()]
                    groupby_sim = groupby_sim[(-groupby_sim).argsort()]
                    gb_sugg = list(
                        groupby_cols[groupby_sim > self.groupby_th])  # similarity thresholds
            gb_sugg += gb_sugg_context
            # print(f"gb_sugg: {gb_sugg}")
            groupby_sugg.append(gb_sugg)
            ################################################################
            # `agg` entity suggestion
            # TODO: Thresholds `agg` confidence support and similarity
            agg_df = pd.DataFrame(agg_list).head()
            # print(agg_df.head())
            agg_sugg_dict = {}
            if len(col_mul_idx) > 0:
                for agg_opt in agg_opts:
                    # calculate `agg` context relevance
                    ################################################################
                    agg_l = [agg_c[agg_opt] for agg_c in agg_contexts if agg_opt in agg_c.keys()]
                    agg_l = np.concatenate(agg_l) if len(agg_l) > 0 else agg_l
                    if len(agg_l) > 0:
                        agg_context_sim = np.max(self.cal_cosine_sim(agg_l, col), axis=0)
                        agg_col = [col[aid] for aid, a_sim in enumerate(agg_context_sim) if
                                   a_sim > self.item_sim]
                        if agg_opt not in agg_sugg_dict.keys():
                            agg_sugg_dict[agg_opt] = []
                        agg_sugg_dict[agg_opt] += (agg_col)
                        # print("type(agg_col)",type(agg_col), agg_col)
                    ################################################################
                    # calculate db `agg` relevance
                    agg_num = 0
                    a_l = []
                    for agg in agg_df[agg_opt].values:
                        if len(agg) > 0:
                            agg_num += 1
                            a_l += agg
                    if agg_num / len(col_mul_idx) > self.agg_th:
                        # agg_sugg_dict[agg_opt] = []
                        groupby_sim = np.max(self.cal_cosine_sim(a_l, col), axis=0)
                        for g_sim, c in zip(groupby_sim, col):
                            if g_sim > self.agg_th:
                                if agg_opt not in agg_sugg_dict.keys():
                                    agg_sugg_dict[agg_opt] = []
                                if c not in agg_sugg_dict[agg_opt]:
                                    agg_sugg_dict[agg_opt].append(c)
            agg_sugg.append(agg_sugg_dict)
        # assert len(agg_sugg) == len(cols)
        # print("agg_sugg: ", agg_sugg)
        return groupby_sugg, agg_sugg

    def query_suggestion(self, db_df_bin, context_dict={"select": [], "groupby": [], "agg": []},
                         min_support=None, top_n=3):
        """
        TODO: 
        1. consider clustering input columns based on their semantics and operate cols on cluster levels
        2. consider user specified (combo of interest) that are not frequently seen in the db
        3. IMPLICIT feedback: selection of recomended items, indicating items that are not selected is not of users' interest,
        consider decreasing the rank of unselected recommended items
        4. ranking considering `groupby` and `opt` items
        """
        support = self.item_sim if min_support is None else min_support
        # `select`, `agg`, `groupby`
        sel_contexts = context_dict["select"]
        agg_contexts = context_dict["agg"]
        groupby_contexts = context_dict["groupby"]
        # initial recommendation
        if len(sel_contexts) == 0:
            freq_combo = self.get_freq_combo(db_df_bin, set([]), support)
            union_set = frozenset().union(*freq_combo["itemsets"].values)
            next_cols = [list(v) for v in freq_combo["itemsets"].values]
            if len(union_set) < top_n:
                cols_supp = [[col] for col in db_df_bin.columns.difference(list(union_set))[
                                              :(top_n - len(union_set))]]
                next_cols += cols_supp
            # get `groupby` and `agg_opt` items
            groupby_sugg, agg_sugg = self.get_opts(db_df_bin, next_cols, groupby_contexts,
                                                   agg_contexts)
            return {
                "select": next_cols,
                "groupby": groupby_sugg,
                "agg": agg_sugg,
            }

        # recommendation considering the contexts information
        columns = db_df_bin.columns
        context_cols = np.concatenate(sel_contexts)
        # print(f"context_cols: {context_cols}")
        rest_cols = columns.difference(context_cols)

        all_sims = np.zeros(len(rest_cols))
        for contextid, context in enumerate(sel_contexts):
            # 1. consider semantic similarity
            semantic_sim_scores = np.max(self.cal_cosine_sim(rest_cols, context),
                                         axis=1) * math.pow(self.alpha,
                                                            len(sel_contexts) - contextid - 1)
            # 2. consider cosine similarity between feature vectors (relevance vector to the database)
            db_col_feat = db_df_bin[rest_cols].T
            context_feat = db_df_bin[context].T
            db_relevance = np.max(cosine_similarity(db_col_feat, context_feat), axis=1) * math.pow(
                self.alpha, len(sel_contexts) - contextid - 1)
            # 3. average similarity based on semantic similarity and db relevance
            all_sims += semantic_sim_scores + self.beta * db_relevance

        top_n_rest_cols = rest_cols[(-all_sims).argsort()][:top_n]
        # TODO: pay attention to item similarity threshold change & reinitialization
        support = self.item_sim * math.pow(self.alpha, len(sel_contexts))
        # print(f"support: {support}")
        # print(f"self.item_sim: {self.item_sim}")
        freq_combo = self.get_freq_combo(db_df_bin[list(context_cols) + list(top_n_rest_cols)],
                                         filter_set=set(context_cols), support=support)
        freq_cols = [list(v) for v in freq_combo["itemsets"].values if len(v) > 0]
        if len(freq_combo["itemsets"].values) < top_n:
            # print("*"*10)
            # print(top_n_rest_cols, freq_cols)
            # print("*"*10)
            if len(freq_cols) == 0:
                freq_cols = [[tn] for tn in top_n_rest_cols]
            else:
                freq_cols += [[col] for col in top_n_rest_cols if
                              col not in np.concatenate(freq_cols)]

        # get `groupby` and `agg_opt` items
        groupby_sugg, agg_sugg = self.get_opts(db_df_bin, freq_cols, groupby_contexts,
                                               agg_contexts)
        return {
            "select": freq_cols,
            "groupby": groupby_sugg,
            "agg": agg_sugg
        }


if __name__ == "__main__":
    qr = queryRecommender(test_table_cols)
    db_bin = qr.search_sim_dbs(test_topic.replace("_", " ").strip())
    # initial recommendation
    context_dict = {
        "select": [],
        "groupby": [],
        "agg": []
    }
    sugg_dict = qr.query_suggestion(db_bin, context_dict, None)
    freq_combo = sugg_dict["select"]
    groupby_sugg = sugg_dict["groupby"]
    agg_sugg = sugg_dict["agg"]
    select_items = [freq_combo[0]]

    print(f"next_cols: {freq_combo}")
    print(f"groupby_sugg: {groupby_sugg}")
    print(f"agg_sugg: {agg_sugg}")
    print(f"select_items: {select_items}")
    print()

    # next query suggestion
    context_dict["select"] = select_items
    sugg_dict = qr.query_suggestion(db_bin, context_dict, None)
    next_cols = sugg_dict["select"]
    groupby_sugg = sugg_dict["groupby"]
    agg_sugg = sugg_dict["agg"]

    print(f"next_cols: {next_cols}")
    print(f"groupby_sugg: {groupby_sugg}")
    print(f"agg_sugg: {agg_sugg}")
    print(f"select_items: {select_items + [next_cols[0]]}")
    print()

    # next query suggestion
    context_dict["select"] = select_items + [next_cols[0]]
    sugg_dict = qr.query_suggestion(db_bin, context_dict, None)
    next_cols = sugg_dict["select"]
    groupby_sugg = sugg_dict["groupby"]
    agg_sugg = sugg_dict["agg"]
    # print(len(next_cols), len(groupby_sugg))
    print(f"next_cols: {next_cols}")
    print(f"groupby_sugg: {groupby_sugg}")
    print(f"agg_sugg: {agg_sugg}")
