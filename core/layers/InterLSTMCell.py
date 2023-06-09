import mindspore
import mindspore.nn as nn
import x2ms_adapter
import x2ms_adapter.nn as x2ms_nn
__author__ = 'chuyao'

class InterLSTMCell(nn.Cell):
    def __init__(self, in_channel, num_hidden, width, filter_size, stride, layer_norm,r):
        super(InterLSTMCell, self).__init__()

        self.num_hidden = num_hidden
        self.padding = filter_size // 2
        self._forget_bias = 1.0
        self.r = r
        self.conv_x = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(in_channel, num_hidden * 4, kernel_size=filter_size, stride=stride, padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden * 4, width, width])
        )
        self.conv_h = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(num_hidden, num_hidden * 4, kernel_size=filter_size, stride=stride, padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden * 4, width, width])
        )

        self.conv_x_h = []
        self.conv_x_x = []
        self.conv_h_x = []
        self.conv_h_h = []
        
        for i in range(self.r):
            self.conv_x_h.append(
                x2ms_nn.Sequential(
                    x2ms_nn.Conv2d(in_channel, num_hidden, kernel_size=filter_size, stride=stride, padding=self.padding),
                    x2ms_nn.LayerNorm([num_hidden, width, width])
                )
            )
            self.conv_x_x.append(
                x2ms_nn.Sequential(
                    x2ms_nn.Conv2d(in_channel, in_channel, kernel_size=filter_size, stride=stride, padding=self.padding),
                    x2ms_nn.LayerNorm([in_channel, width, width])
                )
            )
            self.conv_h_x.append(
                x2ms_nn.Sequential(
                    x2ms_nn.Conv2d(num_hidden, in_channel, kernel_size=filter_size, stride=stride, padding=self.padding),
                    x2ms_nn.LayerNorm([in_channel, width, width])
                )
            )
            self.conv_h_h.append(
                x2ms_nn.Sequential(
                    x2ms_nn.Conv2d(num_hidden, num_hidden, kernel_size=filter_size, stride=stride, padding=self.padding),
                    x2ms_nn.LayerNorm([num_hidden, width, width])
                )
            )
        self.conv_x_h = x2ms_nn.ModuleList(self.conv_x_h)
        self.conv_x_x = x2ms_nn.ModuleList(self.conv_x_x)
        self.conv_h_x = x2ms_nn.ModuleList(self.conv_h_x)
        self.conv_h_h = x2ms_nn.ModuleList(self.conv_h_h)

    def construct(self, x_t, h_t, c_t):

        for i in range(self.r):
            h_t = x2ms_nn.ReLU()(self.conv_x_h[i](x_t) + self.conv_h_h[i](h_t))
            x_t = x2ms_nn.ReLU()(self.conv_x_x[i](x_t) + self.conv_h_x[i](h_t))

        x_concat = self.conv_x(x_t)
        h_concat = self.conv_h(h_t)

        i_x, f_x, g_x, o_x = x2ms_adapter.split(x_concat, self.num_hidden, dim=1)
        i_h, f_h, g_h, o_h = x2ms_adapter.split(h_concat, self.num_hidden, dim=1)

        i_t = x2ms_adapter.sigmoid(i_x + i_h)
        f_t = x2ms_adapter.sigmoid(f_x + f_h + self._forget_bias)
        g_t = x2ms_adapter.tanh(g_x + g_h)

        c_new = f_t * c_t + i_t * g_t

        o_t = x2ms_adapter.sigmoid(o_x + o_h + c_new)
        h_new = o_t * x2ms_adapter.tanh(c_new)

        return h_new, c_new









