import { useQuery } from '@tanstack/react-query'
import { administrationApi, hasScope } from '@/lib/administration-api'

export function useProductionAccess() {
  const query = useQuery({ queryKey: ['principal'], queryFn: administrationApi.principal })
  return { principal: query.data, canWrite: hasScope(query.data, 'production:write'), canReview: hasScope(query.data, 'production:review') }
}
