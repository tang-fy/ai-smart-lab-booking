<template>
  <div>
    <el-card style="margin-bottom: 16px; border: none">
      <div
        style="
          padding: 24px;
          border-radius: 8px;
          background: linear-gradient(120deg, #5b7cfa 0%, #7f9cf5 45%, #9f7aea 100%);
          color: #fff;
        "
      >
        <div style="font-size: 22px; font-weight: bold">
          欢迎您，{{ userInfo?.name || userInfo?.username || '同学' }}
        </div>
        <div style="margin-top: 8px; font-size: 14px; opacity: 0.9">
          智能实验室预约系统：查实验室、约时段、看审核进度，都可以交给 AI 助手。
        </div>
        <div style="margin-top: 16px; display: flex; gap: 10px">
          <el-button type="primary" plain @click="router.push('/manager/ai-chat')">
            跟 AI 助手聊聊
          </el-button>
          <el-button
            v-if="isStudent"
            plain
            @click="router.push('/manager/lablist')"
          >
            去预约实验室
          </el-button>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #909399; font-size: 13px">实验室总数</div>
          <div style="font-size: 26px; font-weight: bold; margin-top: 8px">{{ stats.labTotal }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #909399; font-size: 13px">设备总数</div>
          <div style="font-size: 26px; font-weight: bold; margin-top: 8px">
            {{ stats.equipmentTotal }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #909399; font-size: 13px">{{ isStudent ? '我的预约' : '预约总数' }}</div>
          <div style="font-size: 26px; font-weight: bold; margin-top: 8px">
            {{ stats.reservationTotal }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div style="color: #909399; font-size: 13px">待审核</div>
          <div style="font-size: 26px; font-weight: bold; margin-top: 8px; color: #e6a23c">
            {{ stats.pendingTotal }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card>
      <template #header>
        <div style="font-size: 16px; font-weight: bold">快捷入口</div>
      </template>
      <el-row :gutter="16">
        <el-col :span="6" v-for="item in entries" :key="item.path" style="margin-bottom: 8px">
          <el-card shadow="hover" style="cursor: pointer" @click="router.push(item.path)">
            <div style="display: flex; align-items: center; gap: 10px">
              <el-icon :size="22" :color="item.color"><component :is="item.icon" /></el-icon>
              <div>
                <div style="font-weight: bold">{{ item.title }}</div>
                <div style="font-size: 12px; color: #909399; margin-top: 4px">
                  {{ item.desc }}
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, DocumentChecked, OfficeBuilding, Tickets } from '@element-plus/icons-vue'
import { useUser } from '@/utils/user'
import { getLabPageList } from '@/api/lab'
import { getEquipmentPageList } from '@/api/equipment'
import { getReservationPageList } from '@/api/reservation'

const router = useRouter()
const { userInfo } = useUser()
const isStudent = computed(() => userInfo.value?.role !== 'admin')

const stats = reactive({
  labTotal: 0,
  equipmentTotal: 0,
  reservationTotal: 0,
  pendingTotal: 0
})

const entries = computed(() => {
  if (isStudent.value) {
    return [
      { title: '实验室列表', desc: '查看实验室并预约', path: '/manager/lablist', icon: OfficeBuilding, color: '#409eff' },
      { title: '我的预约', desc: '查看进度、取消预约', path: '/manager/my-reservation', icon: Tickets, color: '#67c23a' },
      { title: 'AI 智能助手', desc: '问规则、查设备、帮我预约', path: '/manager/ai-chat', icon: ChatDotRound, color: '#9f7aea' },
      { title: '个人中心', desc: '修改资料与头像', path: '/manager/profile', icon: DocumentChecked, color: '#e6a23c' }
    ]
  }
  return [
    { title: '实验室管理', desc: '维护实验室信息', path: '/manager/lab', icon: OfficeBuilding, color: '#409eff' },
    { title: '设备管理', desc: '维护实验室设备', path: '/manager/equipment', icon: Tickets, color: '#67c23a' },
    { title: '预约审核', desc: '通过或拒绝预约', path: '/manager/audit-reservation', icon: DocumentChecked, color: '#e6a23c' },
    { title: 'AI 智能助手', desc: '问规则、查设备、帮我预约', path: '/manager/ai-chat', icon: ChatDotRound, color: '#9f7aea' }
  ]
})

const loadStats = async () => {
  const [labRes, equipmentRes, reservationRes, pendingRes] = await Promise.all([
    getLabPageList({ page: 1, page_size: 1 }).catch(() => null),
    getEquipmentPageList({ page: 1, page_size: 1 }).catch(() => null),
    getReservationPageList({ page: 1, page_size: 1 }).catch(() => null),
    getReservationPageList({ page: 1, page_size: 1, status: 0 }).catch(() => null)
  ])
  if (labRes?.code === 200) stats.labTotal = labRes.data?.total ?? 0
  if (equipmentRes?.code === 200) stats.equipmentTotal = equipmentRes.data?.total ?? 0
  if (reservationRes?.code === 200) stats.reservationTotal = reservationRes.data?.total ?? 0
  if (pendingRes?.code === 200) stats.pendingTotal = pendingRes.data?.total ?? 0
}

onMounted(() => {
  loadStats()
})
</script>
