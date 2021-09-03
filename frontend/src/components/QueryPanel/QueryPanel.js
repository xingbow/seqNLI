import dataService from '../../service/dataService.js'
import pipeService from '../../service/pipeService.js'

export default {
    name: "QueryPanel",
    props: {
        dbselected: "",
        tables: {},
    },
    data() {
        return {
            userText: "",
            popoverVisible: false,
            textOptions: [],
            rowStyle: {
                padding: 2
            },
            showSugg: false,
            qSugg: {},
        }
    },
    watch: {
        dbselected: function(dbselected) {
            // console.log("watch dbselected change!")
            if(dbselected.length>0){
                dataService.SQLSugg(dbselected, (suggData) => {
                    this.qSugg = suggData["nl"];
                    console.log("suggData: ", dbselected, suggData)
                });
            }
        },
    },
    mounted() {
        pipeService.onSetQuery(nl => {
            // console.log("nl in querypanel: ", nl)
            this.userText = nl;
        })
        const vm = this;
        this.$nextTick(() => {
            if(vm.dbselected.length > 0){
                dataService.SQLSugg(vm.dbselected, (suggData) => {
                    console.log("suggestion data: ", suggData);
                    this.qSugg = suggData["nl"];
                });
            } 
        });
    },
    methods: {
        search: function() {
            if (this.userText.length > 0) {
                const userText = this.userText;
                const dbName = this.dbselected;
                // TODO: the logic has been updated to sync (2nd Sep)
                dataService.text2SQL([this.userText, dbName], (data) => {
                    const sqlResult = {
                            "sql": data["sql"].trim(),
                            "data": data["data"],
                            "nl": userText.trim()
                        }
                        // send "sql" to settings and record sql history
                    if (sqlResult["sql"].length > 0) {
                        dataService.SQL2text(sqlResult["sql"], dbName, (data) => {
                            sqlResult.SQLTrans = data;
                            dataService.SQL2VL(sqlResult["sql"], dbName, (data) => {
                                sqlResult.VLSpecs = [data];
                                pipeService.emitSQL(sqlResult);
                            });
                        });

                        // query suggestions
                        dataService.SQLSugg(dbName, (data) => {
                            console.log("query suggestion after submitting nl query: ", data);
                            // pipeService.emitQuerySugg(data);
                            this.qSugg = data['nl'];
                        })
                    } else {
                        alert("sql returns is empty");
                    }
                });
            } else {
                alert("input text is empty");
            }
        },
        onInput: function(input) {
            // console.log(this.textOptions);
            let textOptions = [];
            for (let tableName in this.tables) {
                const columnOptions = this.tables[tableName].map(col => ({
                    type: col[1],
                    colName: col[0],
                    tableName: tableName
                }));
                textOptions = [...textOptions, ...columnOptions];
            }

            const validInput = input.split(',').pop();
            const validOptions = [];
            let tokens = validInput.split(' ');

            // TODO: only consider at most the last three words
            if (tokens.length > 3) {
                tokens = tokens.slice(tokens.length - 3, tokens.length);
            }

            while (tokens.length > 0) {
                const subString = tokens.join(' ');
                for (let optionId in textOptions) {
                    const option = textOptions[optionId];
                    const colName = option.colName;
                    if (colName.match(`^${subString}`)) {
                        option.numToken = tokens.length;
                        validOptions.push(option);
                    }
                }
                tokens = tokens.slice(1, tokens.length);
            }

            this.textOptions = validOptions;
            if (this.textOptions.length > 0) {
                this.popoverVisible = true;
            } else {
                this.popoverVisible = false;
            }
        },

        onBlur: function() {
            this.popoverVisible = false;
        },

        rowClick: function(row, column, event) {
            let tokens = this.userText.split(' ');
            for (let i = 0; i < row.numToken; i++) {
                tokens.pop();
            }
            tokens.push(row.colName);
            this.userText = tokens.join(' ');
        },

        selectQuery: function(nlidx) {
            if (this.qSugg) {
                console.log("receive nl query:", nlidx, this.qSugg[nlidx]);
                pipeService.emitSetQuery(this.qSugg[nlidx]);
            }
        },
    }
}