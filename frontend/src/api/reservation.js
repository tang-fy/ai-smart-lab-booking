import request from '@/utils/request'

/**
 * 创建预约
 * idempotencyKey 同一次提交重试时保持不变，后端据此避免重复预约
 */
export function createReservationApi(data, idempotencyKey) {
  return request({
    url: '/api/reservation',
    method: 'post',
    data,
    headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}
  })
}

/**
 * 查询预约记录
 */
export function getReservationPageList(params) {
  return request({
    url: '/api/reservation/list',
    method: 'get',
    params
  })
}

/**
 * 取消预约
 */
export function cancelReservationApi(id) {
  return request({
    url: `/api/reservation/${id}/cancel`,
    method: 'put'
  })
}

/**
 * 审核预约
 */
export function auditReservationApi(id, status) {
  return request({
    url: `/api/reservation/${id}/audit`,
    method: 'put',
    data: { status }
  })
}
