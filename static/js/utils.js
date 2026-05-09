/**
 * 通用GET请求函数
 * @param {string} url - 请求地址
 * @param {object} params - URL查询参数（键值对）
 * @returns {Promise} 响应结果
 */
export async function requestGet(url, params = {}) {
    try {
        // 拼接参数到URL（如：/api/get_data?key1=val1&key2=val2）
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;

        const response = await fetch(fullUrl, {
            method: 'GET', // GET可省略，因为fetch默认是GET
            headers: {
                // GET请求一般不需要Content-Type（除非有特殊需求）
            }
        });

        // 解析JSON响应（后端返回JSON时用）
        const result = await response.json();
        return result;
    } catch (error) {
        console.error("GET请求失败：", error);
        throw error; // 抛出错误让调用方处理
    }
}

/**
 * 通用POST请求函数
 * @param {string} url - 请求地址
 * @param {object} queryParams - URL查询参数（可选）
 * @param {object} bodyParams - 请求体参数（JSON格式，可选）
 * @returns {Promise} 响应结果
 */
export async function requestPost(url, queryParams = {}, bodyParams = {}) {
    try {
        // 拼接URL查询参数
        const queryString = new URLSearchParams(queryParams).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;

        const response = await fetch(fullUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json', // 传递JSON体必须加这个头
                // 若传表单数据（如文件上传），则改为：'Content-Type': 'multipart/form-data'
                // 若传普通表单，改为：'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: JSON.stringify(bodyParams) // 请求体转JSON字符串
        });

        const result = await response.json();
        return result;
    } catch (error) {
        console.error("POST请求失败：", error);
        throw error;
    }
}

// 从后端获取动态Token的函数
export async function getTokenFromBackend() {
    try {
        const response = await fetch('/api/get_token'); // GET请求获取Token
        const result = await response.json();
        if (result.success) {
            return result.token; // 返回后端的动态Token
        } else {
            showError("获取Token失败：" + result.message);
            return null;
        }
    } catch (error) {
        showError("获取Token异常：" + error.message);
        return null;
    }
}