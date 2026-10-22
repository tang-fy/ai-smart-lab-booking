import requset from '@/utils/request'

//获取当前登录用户

export function getUserInfo() {
  return requset({
    url: '/api/user/me',
    method: 'get'
  })
}

//修改个人信息

export function updateUserInfo(data) {
  return requset({
    url: '/api/user/me',
    method: 'put',
    data
  })
}

//修改密码

export function updatePasswordApi(data) {
  return requset({
    url: '/api/user/password',
    method: 'put',
    data
  })
}

//分页模糊查询用户列表

export function getUserPageList(params) {
  return requset({
    url: '/api/user/list',
    method: 'get',
    params
  })
}

//新增用户

export function createUserApi(data) {
  return requset({
    url: '/api/user',
    method: 'post',
    data
  })
}

//更改用户信息

export function updateUserApi(userId, data) {
  return requset({
    url: `/api/user/${userId}`, // f"xxxx{xxxxx}模板
    method: 'put',
    data
  })
}

//删除用户

export function deleteUserApi(userId) {
  return requset({
    url: `/api/user/${userId}`,
    method: 'delete'
  })
}
