  Input: grocery_builder output                                                                                              
                                                                                                                             
  By the time price_optimizer runs, grocery_builder has already produced a grocery_list — every ingredient from every recipe 
  across 28 meal slots, aggregated by name/unit, diffed against the fridge. Each GroceryItem has:                            
  - quantity — total needed across all recipes                            
  - shopping_quantity — what you still need to buy (quantity - quantity_in_fridge)                                           
  - already_have — true if the fridge fully covers it                             
  - source_recipe_ids — traceability back to which recipes need this item                                                    
                                                                                                                             
  Items with already_have=True or shopping_quantity <= 0 are excluded from pricing entirely.                                 
                                                                                                                             
  Step 1: Collect quotes from all stores in parallel                                                                         
                                                                                                                             
  Three mock store adapters run concurrently — InstacartAdapter, MockWalmartAdapter, MockCostcoAdapter. Each returns a       
  StoreQuote per grocery item with price, unit_price, in_stock, delivery_fee, and min_order.
                                                                                                                             
  The prices aren't random. Each adapter has a deterministic pricing model driven by:                                        
  - Category base costs — meat is expensive (~$0.98/unit), pantry is cheap (~$0.38/unit), with keyword adjustments (salmon
  2.6x, rice 0.8x, etc.)                                                                                                     
  - Store-specific markup — Walmart is cheapest (0.98 × 0.92 = ~0.90x), Costco is slightly cheaper on unit price (0.94 × 0.86
   = ~0.81x) but has bulk modifiers, Instacart is most expensive (1.18 × 1.08 = ~1.27x)                                      
  - Stable hash-based variance — sha256(store::item_name::price) generates a per-item-per-store variance so the same item    
  always gets the same price at the same store across runs                                                               
  - Stock availability — same hash approach with a stock floor (Walmart 94% chance in stock, Costco 88%, Instacart 90%)      
  - Store constraints — Instacart: $8.99 delivery / $18 minimum. Walmart: $5.99 / $22. Costco: $10.99 / $30.           
                                                                                                                             
  If an adapter throws, it retries once with a short backoff, then the system continues with partial store coverage.         
                                                                                                                             
  Step 2: Rank items by cheapest available quote                                                                             
                                                                                                                             
  rank_by_price finds each item's cheapest in-stock quote across all stores and stamps best_store and best_price onto the    
  GroceryItem. This is the per-item cheapest, not the global optimum — it doesn't account for delivery fees or minimum orders
   yet.                                                                                                                      
                                                                          
  Step 3: Calculate store summaries

  calculate_store_totals builds a StoreSummary per store: how many items that store can cover, the subtotal if you bought    
  everything there, the delivery fee, and whether it meets its own minimum order. This is the "what if you bought everything
  at store X" view.                                                                                                          
                                                                          
  Step 4: Build candidate purchase plans                                                                                     
   
  This is where the predetermined baskets come from. The system generates up to ~8 candidate plans combinatorially:          
                                                                          
  Split strategies (buy each item at its cheapest store):                                                                    
  - split_online — each item goes to its cheapest store, all orders are delivery
  - split_in_store — same item-store mapping, but all channels forced to in_store (no delivery fees)                         
                                                                                                    
  Single-store strategies (buy everything at one store, only if that store has all items in stock):                          
  - {store}_online — everything at one store with delivery                                                                   
  - {store}_in_store — everything at one store, pick up in person                                                            
                                                                                                                             
  So with 3 stores you could get: split_online, split_in_store, walmart_online, walmart_in_store, instacart_online,          
  instacart_in_store, costco_online, costco_in_store.                                                                        
                                                                                                                             
  A candidate is discarded if missing_priced_items finds any required item without a purchase order line — i.e., it can't    
  actually cover the full basket. Single-store plans are only built for stores where all_items_available is true.
                                                                                                                             
  Each CandidatePurchasePlan carries: strategy name, rationale string, the actual PurchaseOrder objects, total cost, store   
  count, and online order count.
                                                                                                                             
  Step 5: Choose one plan                                                 

  Two-tier selection:                                                                                                        
   
  Heuristic fallback (_heuristic_plan_choice): Filters to affordable plans (within budget_weekly). Among those within $6 of  
  the cheapest, it sorts by user schedule fit:                            
  - If the user's schedule has time-constrained keywords ("quick", "busy", "15", "20", "30"), prefer online delivery and     
  fewer stores                                                                                                               
  - Otherwise, prefer fewer stores and lower cost, with a slight preference for in-store (no fees)
                                                                                                                             
  LLM choice (_llm_plan_choice): If a chat model is configured, it sends the user profile summary, schedule, grocery list,   
  store summaries, and all candidate plans (with costs and budget flags) to the LLM with the price_tradeoff.md prompt. The   
  LLM picks a plan_id and gives a rationale.                                                                                 
                                                                                                                             
  Deterministic budget guard: If the LLM picks a plan that's over budget but affordable plans exist, the system overrides to 
  the cheapest affordable plan and appends an explanation.
                                                                                                                             
  If no chat model is configured (like in tests), the heuristic alone decides.                                               
   
  Step 6: Finalize                                                                                                           
                                                                          
  The chosen plan's PurchaseOrder objects become the final purchase orders. Each order has a store, channel                  
  (online/in_store), item list with prices, subtotal, delivery fee, and total. check_budget produces the BudgetSummary (total
   cost vs. weekly budget, overage, utilization ratio). The grocery list items get stamped with their final best_store,      
  best_price, and buy_online from the selected orders.                    

  If there are missing items or the budget is blown, _build_replan_reason produces a reason string that propagates to the    
  critic, which can then trigger a repair loop.
                                                                                                                             
  The key artifacts                                                                                                          
   
  - StoreQuote — one per item per store: "Walmart can sell you 2 lbs chicken breast for $5.49, in stock, $5.99 delivery fee, 
  $22 minimum"                                                            
  - StoreSummary — one per store: "Walmart can cover 18/20 items, subtotal $47.30, total with delivery $53.29, meets minimum 
  order"                                                                                                                     
  - CandidatePurchasePlan — a complete basket allocation: "split_online: chicken at Walmart, rice at Costco, ..., total
  $52.18 across 2 stores"                                                                                                    
  - PurchaseOrder — the winning plan's concrete orders: "Order 1: Walmart online, 12 items, $31.20 + $5.99 delivery = $37.19"
  - BudgetSummary — "Budget $140, total cost $52.18, within budget, 37% utilization"   

TODO: 
- User preference input needed: No hybrid option only online or in store only.
- Some better optimization/option exploration than the pre-determined baskets: cost, store count, distance, in-store or online
- Why are there multiple purchase plans? Thought it was deterministic based on cheapest prices that follows the items. Only reasoning choice is if on hybrid mode reason about what to get in store vs online. Even that can be deterministic rules? what other strategy than lowest price?
- Edge case: small order from one store bumps cost higher than if individual order higher on another store. Or if they have discounts on purchase thresholds?