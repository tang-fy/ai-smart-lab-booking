import requset from '@/utils/request'

//分页模糊查询列表

export function getEquipmentPageList(params) {
  return requset({
    url: '/api/equipment/list',
    method: 'get',
    params
  })
}

//新增

export function createEquipmentApi(data) {
  return requset({
    url: '/api/equipment',
    method: 'post',
    data
  })
}

//更改

export function updateEquipmentApi(equipmentId, data) {
  return requset({
    url: `/api/equipment/${equipmentId}`, // f"xxxx{xxxxx}模板
    method: 'put',
    data
  })
}

//删除

export function deleteEquipmentApi(equipmentId) {
  return requset({
    url: `/api/equipment/${equipmentId}`,
    method: 'delete'
  })
}
