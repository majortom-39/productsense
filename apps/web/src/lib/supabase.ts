import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!url || !anonKey) {
  // Don't throw at module load — let the app render and surface a clear error.
  console.warn(
    "[productsense] VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY missing. Auth + persistence will not work until set in apps/web/.env."
  );
}

export const supabase = createClient(url ?? "", anonKey ?? "", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
  },
});
