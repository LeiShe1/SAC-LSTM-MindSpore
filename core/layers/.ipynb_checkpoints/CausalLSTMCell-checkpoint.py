import mindspore
import mindspore.nn as nn
import x2ms_adapter
import x2ms_adapter.nn as x2ms_nn


class CausalLSTMCell(nn.Cell):
    def __init__(self,
                 in_channel,
                 num_hidden_in,
                 num_hidden,
                 height,
                 width,
                 filter_size,
                 stride,
                 layer_norm,
                 ):
        super(CausalLSTMCell, self).__init__()

        self.at_in_dim = num_hidden
        # print(self.at_in_dim)
        self.query_conv = x2ms_nn.Conv2d(in_channels = self.at_in_dim, out_channels = self.at_in_dim//8, kernel_size= 1)
        self.key_conv = x2ms_nn.Conv2d(in_channels = self.at_in_dim, out_channels = self.at_in_dim//8, kernel_size= 1)
        self.value_conv = x2ms_nn.Conv2d(in_channels = self.at_in_dim, out_channels = self.at_in_dim, kernel_size= 1)
        self.gamma = mindspore.Parameter(x2ms_adapter.zeros(1))
        self.softmax  = x2ms_nn.Softmax(dim=-1)

        self.num_hidden = num_hidden
        self.padding = filter_size // 2
        self._forget_bias = 1.0
        self.in_channel = in_channel
        self.num_hidden_in = num_hidden_in
        self.conv_x = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(in_channel,
                      num_hidden * 7,
                      kernel_size=filter_size,
                      stride=stride,
                      padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden * 7, height, width]))
        self.conv_h = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(num_hidden,
                      num_hidden * 4,
                      kernel_size=filter_size,
                      stride=stride,
                      padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden * 4, height, width]))
        self.conv_m = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(num_hidden_in,
                      num_hidden * 3,
                      kernel_size=filter_size,
                      stride=stride,
                      padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden * 3, height, width]))
        self.conv_c = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(num_hidden,
                      num_hidden * 3,
                      kernel_size=filter_size,
                      stride=stride,
                      padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden * 3, height, width]))
        self.conv_c2m = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(num_hidden,
                      num_hidden * 4,
                      kernel_size=filter_size,
                      stride=stride,
                      padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden * 4, height, width]))
        self.conv_om = x2ms_nn.Sequential(
            x2ms_nn.Conv2d(num_hidden,
                      num_hidden,
                      kernel_size=filter_size,
                      stride=stride,
                      padding=self.padding),
            x2ms_nn.LayerNorm([num_hidden, height, width]))

        self.conv_last = x2ms_nn.Conv2d(num_hidden * 2,
                                   num_hidden,
                                   kernel_size=1,
                                   stride=1,
                                   padding=0)


    def construct(self, x_t, h_t, c_t, m_t):


        x_concat = self.conv_x(x_t)
        h_concat = self.conv_h(h_t)
        m_concat = self.conv_m(m_t)
        c_concat = self.conv_c(c_t)
        i_x, f_x, g_x, i_x_prime, f_x_prime, g_x_prime, o_x = x2ms_adapter.split(
            x_concat, self.num_hidden, dim=1)
        i_h, f_h, g_h, o_h = x2ms_adapter.split(h_concat, self.num_hidden, dim=1)
        i_m, f_m, g_m = x2ms_adapter.split(m_concat, self.num_hidden, dim=1)
        i_c, f_c, g_c = x2ms_adapter.split(c_concat, self.num_hidden, dim=1)

        i_t = x2ms_adapter.sigmoid(i_x + i_h + i_c)
        f_t = x2ms_adapter.sigmoid(f_x + f_h + f_c + self._forget_bias)
        g_t = x2ms_adapter.tanh(g_x + g_h + g_c)

        c_new = f_t * c_t + i_t * g_t
        c2m_concat = self.conv_c2m(c_new)
        i_c, g_c, f_c, o_c = x2ms_adapter.split(c2m_concat, self.num_hidden, dim=1)

        i_t_prime = x2ms_adapter.sigmoid(i_x_prime + i_m + i_c)
        f_t_prime = x2ms_adapter.sigmoid(f_x_prime + f_m + f_c + self._forget_bias)
        g_t_prime = x2ms_adapter.tanh(g_x_prime + g_c)

        m_new = f_t_prime * x2ms_adapter.tanh(g_m) + i_t_prime * g_t_prime
        o_m = self.conv_om(m_new)

        o_t = x2ms_adapter.tanh(o_x + o_h + o_c + o_m)
        cell = x2ms_adapter.cat([c_new, m_new], 1)

        h_new = o_t * x2ms_adapter.tanh(self.conv_last(cell))

        m_batchsize,C,width ,height = x2ms_adapter.tensor_api.x2ms_size(h_new)
        # print(h_new.shape)
        # print(self.query_conv)
        proj_query  = x2ms_adapter.tensor_api.permute(x2ms_adapter.tensor_api.view(self.query_conv(h_new), m_batchsize,-1,width*height), 0,2,1)
        proj_key =  x2ms_adapter.tensor_api.view(self.key_conv(h_new), m_batchsize,-1,width*height)
        energy =  x2ms_adapter.bmm(proj_query,proj_key)
        attention = self.softmax(energy)
        proj_value = x2ms_adapter.tensor_api.view(self.value_conv(h_new), m_batchsize,-1,width*height)
        
        out = x2ms_adapter.bmm(proj_value,x2ms_adapter.tensor_api.permute(attention, 0,2,1))
        out = x2ms_adapter.tensor_api.view(out, m_batchsize,C,width,height)
        
        _h_new = self.gamma*out + h_new


        return _h_new, c_new, m_new
