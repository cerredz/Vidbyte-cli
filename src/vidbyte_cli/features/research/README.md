# Research feature

Research threads are persistent portfolios. Runs add work to a thread; sources and
artifacts remain addressable without being inserted into later model context implicitly.

`domain/` owns wire-independent vocabulary and policy. `application/` owns orchestration
against gateway ports. `commands/` and `presentation/` own the user and output contracts.
`infrastructure/` is the only package that knows Vidbyte research routes or wire DTOs.
