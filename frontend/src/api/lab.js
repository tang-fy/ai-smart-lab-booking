import requset from '@/utils/request'

//分页模糊查询列表

export function getLabPageList(params) {
  return requset({
    url: '/api/lab/list',
    method: 'get',
    params
  })
}

export function getLab(lab_id) {
  return requset({
    url: `/api/lab/${lab_id}`,
    method: 'get'
  })
}

//新增

export function createLabApi(data) {
  return requset({
    url: '/api/lab',
    method: 'post',
    data
  })
}

//更改

export function updateLabApi(labId, data) {
  return requset({
    url: `/api/lab/${labId}`, // f"xxxx{xxxxx}模板
    method: 'put',
    data
  })
}

//删除

export function deleteLabApi(labId) {
  return requset({
    url: `/api/lab/${labId}`,
    method: 'delete'
  })
}
