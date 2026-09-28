module github.com/matteus8/neuron-cupboard-core/gateway

go 1.27.1

require (
	github.com/matteus8/neuron-cupboard-core/proto v0.0.0
	google.golang.org/protobuf v1.36.12
)

replace github.com/matteus8/neuron-cupboard-core/proto => ../proto
