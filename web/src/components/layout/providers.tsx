"use client";

import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";

const CURRENT_USER_KEY = "shopper.currentUserId";

type CurrentUserContextValue = {
  userId: string | null;
  isHydrated: boolean;
  setUserId: (userId: string | null) => void;
  clearUserId: () => void;
};

const CurrentUserContext = createContext<CurrentUserContextValue | null>(null);

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  const [userId, setUserIdState] = useState<string | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(CURRENT_USER_KEY);
    setUserIdState(stored);
    setIsHydrated(true);

    const handleStorage = (event: StorageEvent) => {
      if (event.key === CURRENT_USER_KEY) {
        setUserIdState(event.newValue);
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const setUserId = (nextUserId: string | null) => {
    setUserIdState(nextUserId);

    if (nextUserId) {
      window.localStorage.setItem(CURRENT_USER_KEY, nextUserId);
    } else {
      window.localStorage.removeItem(CURRENT_USER_KEY);
    }
  };

  return (
    <QueryClientProvider client={queryClient}>
      <CurrentUserContext.Provider
        value={{
          userId,
          isHydrated,
          setUserId,
          clearUserId: () => setUserId(null),
        }}
      >
        {children}
      </CurrentUserContext.Provider>
    </QueryClientProvider>
  );
}

export function useCurrentUser() {
  const context = useContext(CurrentUserContext);

  if (!context) {
    throw new Error("useCurrentUser must be used within the app Providers.");
  }

  return context;
}
