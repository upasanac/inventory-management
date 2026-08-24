<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="budget-control">
          <label class="budget-label" for="budget-slider">{{ t('restocking.budgetLabel') }}</label>
          <input
            id="budget-slider"
            type="range"
            min="0"
            max="10000"
            step="100"
            v-model.number="budget"
            class="budget-slider"
          />
          <span class="budget-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.itemsCovered') }}</div>
          <div class="stat-value">{{ itemsCovered }} / {{ totalEligibleItems }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ totalCost.toLocaleString() }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ remainingBudget.toLocaleString() }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.leadTime') }}</div>
          <div class="stat-value">{{ t('restocking.leadTimeDays', { days: leadTimeDays }) }}</div>
        </div>
      </div>

      <div v-if="successMessage" class="success-banner">
        <span>{{ successMessage }}</span>
        <button class="link-btn" @click="goToOrders">{{ t('restocking.viewInOrders') }}</button>
      </div>

      <div v-if="submitError" class="error">{{ submitError }}</div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }}</h3>
          <button
            class="btn-primary"
            :disabled="recommendations.length === 0 || placing"
            @click="placeOrder"
          >
            {{ placing ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="!refreshing && recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.warehouse') }}</th>
                <th>{{ t('restocking.table.currentDemand') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.recommendedQty') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendations" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td>{{ item.category }}</td>
                <td>{{ item.warehouse }}</td>
                <td>{{ item.current_demand }}</td>
                <td>{{ item.forecasted_demand }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td>{{ item.recommended_quantity }}</td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toLocaleString() }}</td>
                <td><strong>{{ currencySymbol }}{{ item.line_total.toLocaleString() }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()
    const router = useRouter()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const refreshing = ref(false)
    const error = ref(null)

    const budget = ref(2000)
    const recommendations = ref([])
    const totalCost = ref(0)
    const remainingBudget = ref(0)
    const itemsCovered = ref(0)
    const totalEligibleItems = ref(0)
    const leadTimeDays = ref(14)

    const placing = ref(false)
    const successMessage = ref('')
    const submitError = ref('')

    const { selectedLocation, selectedCategory, selectedPeriod, getCurrentFilters } = useFilters()

    let debounceTimer = null

    const loadRecommendations = async (isFirstLoad) => {
      try {
        if (isFirstLoad) {
          loading.value = true
        } else {
          refreshing.value = true
        }
        error.value = null

        const filters = getCurrentFilters()
        const response = await api.getRestockRecommendations(budget.value, {
          warehouse: filters.warehouse,
          category: filters.category
        })

        recommendations.value = response.recommendations || []
        totalCost.value = response.total_cost || 0
        remainingBudget.value = response.remaining_budget || 0
        itemsCovered.value = response.items_covered || 0
        totalEligibleItems.value = response.total_eligible_items || 0
        leadTimeDays.value = response.lead_time_days || 14
      } catch (err) {
        error.value = 'Failed to load restock recommendations: ' + err.message
      } finally {
        loading.value = false
        refreshing.value = false
      }
    }

    const clearBanners = () => {
      successMessage.value = ''
      submitError.value = ''
    }

    const scheduleReload = () => {
      clearBanners()
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadRecommendations(false)
      }, 400)
    }

    watch(budget, scheduleReload)

    watch([selectedLocation, selectedCategory], () => {
      clearBanners()
      loadRecommendations(false)
    })

    const placeOrder = async () => {
      placing.value = true
      submitError.value = ''
      successMessage.value = ''
      try {
        const filters = getCurrentFilters()
        await api.submitRestockOrder({
          budget: budget.value,
          warehouse: filters.warehouse,
          category: filters.category
        })
        successMessage.value = t('restocking.orderPlacedSuccess', { days: leadTimeDays.value })
        selectedPeriod.value = 'all'
        await loadRecommendations(false)
      } catch (err) {
        submitError.value = 'Failed to place order: ' + err.message
      } finally {
        placing.value = false
      }
    }

    const goToOrders = () => {
      router.push('/orders')
    }

    onMounted(() => loadRecommendations(true))
    onUnmounted(() => {
      if (debounceTimer) clearTimeout(debounceTimer)
    })

    return {
      t,
      loading,
      refreshing,
      error,
      budget,
      currencySymbol,
      recommendations,
      totalCost,
      remainingBudget,
      itemsCovered,
      totalEligibleItems,
      leadTimeDays,
      placing,
      successMessage,
      submitError,
      placeOrder,
      goToOrders
    }
  }
}
</script>

<style scoped>
.budget-control {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  white-space: nowrap;
}

.budget-slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  border-radius: 999px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  transition: background 0.2s;
}

.budget-slider::-webkit-slider-thumb:hover {
  background: #2563eb;
}

.budget-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  transition: background 0.2s;
}

.budget-slider::-moz-range-thumb:hover {
  background: #2563eb;
}

.budget-slider::-moz-range-progress {
  background: #3b82f6;
  height: 6px;
  border-radius: 999px;
}

.budget-slider:focus::-webkit-slider-thumb {
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
}

.budget-value {
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 90px;
  text-align: right;
}

.btn-primary {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.5rem 1.25rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.empty-state {
  text-align: center;
  padding: 2.5rem 1rem;
  color: #64748b;
  font-size: 0.938rem;
}

.success-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 1rem 1.25rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
}

.link-btn {
  background: none;
  border: none;
  color: #065f46;
  font-weight: 700;
  text-decoration: underline;
  cursor: pointer;
  font-size: 0.875rem;
  flex-shrink: 0;
}

.link-btn:hover {
  color: #047857;
}
</style>
