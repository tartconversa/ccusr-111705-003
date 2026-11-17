"""本地业务页面交互。"""

def detail_fragment(item):
    return '<input id="address" list="areas"><datalist id="areas"><option value="桐花苑 1 栋"><option value="桐花苑 2 栋"></datalist><button id="address-check">查询上门范围</button><output id="address-result"></output><script>document.querySelector(\'#address-check\').onclick=()=>{let address=document.querySelector(\'#address\').value;document.querySelector(\'#address-result\').textContent=address===\'桐花苑 1 栋\'?\'桐花苑 1 栋：服务区\':\'地址未确认\'};</script>'
