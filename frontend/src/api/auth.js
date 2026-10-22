import requset from '@/utils/request'

//登录请求

export function loginApi(data) {
  return requset({
    url: 'api/auth/login',
    method: 'post',
    data
  })
}

//注册请求

export function registerApi(data) {
  return requset({
    url: 'api/auth/register',
    method: 'post',
    data
  })
}
