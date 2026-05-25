# Optimizely Configured Commerce — Common Patterns

## Handler Pipeline
- Handlers implement `IHandler<TParameter, TResult>`
- Pipeline: GetCartHandler → ValidateCartHandler → UpdateCartHandler
- Always check: `handler.NextHandler?.Execute(parameter)`

## Common Errors
- NullReferenceException in handlers: check `parameter.Cart != null`
- ElasticSearch index mismatch: re-run full index rebuild
- ISC widget not loading: check webpack build + bundle registration

## Key Services
- IProductService — product retrieval
- ICartService — cart operations
- ICustomerService — customer/session
- IWebsiteService — multi-site config

## Debugging Checklist
1. Check IIS application pool recycled?
2. Check ElasticSearch cluster health: `GET /_cluster/health`
3. Check SQL connection string in Web.config
4. Check handler registration in DependencyConfig.cs
